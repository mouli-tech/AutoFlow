import json
import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from openai import OpenAI

from autoflow.config import AI_SETTINGS_FILE
from autoflow.api.system_context import get_system_context

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/ai", tags=["ai"])

class AISettings(BaseModel):
    provider: str = Field(..., description="Provider name: 'ollama' or 'openai'")
    api_key: str = Field(..., description="API Key for OpenAI. For Ollama this can be blank")
    model: str = Field(..., description="Model name (e.g. 'qwen2.5:1.5b' or 'gpt-4o-mini')")

class GenerateRequest(BaseModel):
    prompt: str

@router.get("/settings", response_model=AISettings)
def get_settings():
    if AI_SETTINGS_FILE.exists():
        try:
            data = json.loads(AI_SETTINGS_FILE.read_text())
            return AISettings(**data)
        except Exception as e:
            log.error(f"Failed to read AI settings: {e}")
    # Default settings
    return AISettings(provider="ollama", api_key="", model="qwen2.5:1.5b")

@router.post("/settings")
def save_settings(settings: AISettings):
    try:
        AI_SETTINGS_FILE.write_text(settings.model_dump_json())
        return {"status": "success"}
    except Exception as e:
        log.error(f"Failed to save AI settings: {e}")
        raise HTTPException(status_code=500, detail="Failed to save settings")

SYSTEM_PROMPT = """You are AutoFlow, a workflow automation tool. Convert user requests into a JSON workflow.
Return ONLY valid JSON. No markdown. No comments. No explanation.

STRICT JSON format:
{"name":"workflow title","description":"short desc","trigger":{"type":"manual"},"steps":[{"name":"step 1","type":"TYPE","args":{ARGS}},{"name":"step 2","type":"TYPE","args":{ARGS}}]}

CRITICAL: Break down EVERY distinct action into its OWN separate step. Each step does ONE thing only.
- Opening an app = 1 step
- Switching a git branch = 1 step
- Running a command = 1 step
- Opening a URL = 1 step
A request with 5 actions MUST produce 5 steps. NEVER combine multiple actions into one step.

TYPE and ARGS must be EXACTLY one of these:

type "open_app" args: {"command":"APP_NAME","args":"OPTIONAL_ARGS"}
type "run_command" args: {"command":"SHELL_CMD","timeout":60,"cwd":"/working/dir"}
type "open_url" args: {"url":"https://example.com"}
type "notify" args: {"title":"Title","message":"Body","urgency":"normal"}

trigger types: "manual", "cron", "login"
For cron add: "schedule":"0 9 * * 1-5"

MULTI-STEP EXAMPLE:
User: "open vscode, go to my-project directory, switch to dev branch, and run tests"
Output: {"name":"Dev Setup","description":"Open VS Code and run tests on dev branch","trigger":{"type":"manual"},"steps":[{"name":"Open VS Code","type":"open_app","args":{"command":"code","args":"~/my-project"}},{"name":"Switch to dev branch","type":"run_command","args":{"command":"git checkout dev","timeout":30,"cwd":"~/my-project"}},{"name":"Run tests","type":"run_command","args":{"command":"npm test","timeout":120,"cwd":"~/my-project"}}]}

RULES:
- EVERY action the user mentions = a SEPARATE step. Do NOT merge actions.
- For desktop apps (pycharm, vscode, firefox): use "open_app"
- For shell commands (cd, git, npm, python): use "run_command"
- Use EXACT directory names and paths the user provides. Do NOT guess or invent paths.
- If the user says "go to X directory", use "cwd" set to that directory path. Do NOT use "cd" as a run_command — set "cwd" instead.
- "timeout" must be a number, not a string.
- For IDE run configurations: check IDE_RUN_CONFIGS in USER SYSTEM context. If a matching config exists, use its ACTUAL command and cwd as a "run_command" step. For Python configs use the python script path. For Shell configs use the shell command text. Do NOT invent config names — only use configs listed in IDE_RUN_CONFIGS.
- Always fill ALL fields. Never leave args empty.
- Use real paths from USER SYSTEM context below when they match what the user describes.
- Return ONLY the JSON object. Nothing else."""

@router.post("/generate")
def generate_workflow(request: GenerateRequest):
    settings = get_settings()
    
    if settings.provider.lower() == "ollama":
        client = OpenAI(
            base_url="http://localhost:11434/v1",
            api_key="ollama"
        )
    else:
        if not settings.api_key:
            raise HTTPException(status_code=400, detail="API Key is required for OpenAI")
        client = OpenAI(api_key=settings.api_key)

    try:
        extra_kwargs = {}
        if settings.provider.lower() == "ollama":
            extra_kwargs["extra_body"] = {"num_predict": 2048}
        
        response = client.chat.completions.create(
            model=settings.model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT + "\n\nUSER SYSTEM:\n" + get_system_context()},
                {"role": "user", "content": request.prompt}
            ],
            temperature=0.1,
            **extra_kwargs
        )
        content = response.choices[0].message.content.strip()
        log.info(f"Raw LLM output: {content[:500]}")
        
        # Clean up markdown
        if content.startswith("```json"):
            content = content[7:]
        if content.startswith("```"):
            content = content[3:]
        if content.endswith("```"):
            content = content[:-3]
            
        content = content.strip()

        if not content:
            raise HTTPException(
                status_code=500,
                detail="AI returned empty response after removing markdown fences",
            )

        parsed = json.loads(content)
        
        # Normalize: the small LLM may return partial structures
        result = normalize_workflow(parsed, request.prompt)
        return result
        
    except json.JSONDecodeError as e:
        log.error(f"LLM returned invalid JSON: {content}")
        raise HTTPException(status_code=500, detail="AI returned invalid JSON format")
    except Exception as e:
        log.error(f"Generation failed: {e}")
        raise HTTPException(status_code=500, detail=f"Generation failed: {str(e)}")

def normalize_workflow(parsed, prompt: str) -> dict:
    """Normalize incomplete LLM output into a full workflow structure."""
    
    # Case 1: LLM returned a single step object (has "type" and "args" but no "steps")
    if isinstance(parsed, dict) and "type" in parsed and "args" in parsed and "steps" not in parsed:
        return {
            "name": parsed.get("name", "Generated Workflow"),
            "description": f"AI-generated from: {prompt[:80]}",
            "trigger": {"type": "manual"},
            "steps": [parsed]
        }
    
    # Case 2: LLM returned an array of steps
    if isinstance(parsed, list):
        return {
            "name": "Generated Workflow",
            "description": f"AI-generated from: {prompt[:80]}",
            "trigger": {"type": "manual"},
            "steps": parsed
        }
    
    # Case 3: LLM returned a workflow but missing some keys
    if isinstance(parsed, dict):
        if "steps" not in parsed:
            parsed["steps"] = []
        if "name" not in parsed:
            parsed["name"] = "Generated Workflow"
        if "description" not in parsed:
            parsed["description"] = f"AI-generated from: {prompt[:80]}"
        if "trigger" not in parsed:
            parsed["trigger"] = {"type": "manual"}
        return parsed
    
    # Fallback
    return {
        "name": "Generated Workflow",
        "description": f"AI-generated from: {prompt[:80]}",
        "trigger": {"type": "manual"},
        "steps": []
    }

class OllamaRequest(BaseModel):
    model_name: str

@router.get("/ollama/check")
def check_ollama_model(model: str):
    try:
        import subprocess
        result = subprocess.run(["ollama", "list"], capture_output=True, text=True)
        if result.returncode != 0:
            return {"installed": False, "error": "Ollama CLI not found or errored"}
        
        # Check if the exact model exists in the list
        installed = False
        for line in result.stdout.splitlines()[1:]:
            parts = line.split()
            if not parts:
                continue
            installed_model = parts[0]
            # Handle tags e.g qwen2.5:1.5b vs qwen2.5 (assumes latest)
            if installed_model == model or installed_model == f"{model}:latest":
                installed = True
                break
                
        return {"installed": installed}
    except Exception as e:
        log.error(f"Failed to check ollama model: {e}")
        return {"installed": False, "error": str(e)}

@router.post("/ollama/pull")
def pull_ollama_model(req: OllamaRequest):
    try:
        import subprocess
        # Run pull in foreground so it blocks until downloaded
        # A real app might stream this async, but block is fine for simplicity here
        result = subprocess.run(["ollama", "pull", req.model_name], capture_output=True, text=True)
        if result.returncode != 0:
            log.error(f"Ollama pull failed: {result.stderr}")
            raise HTTPException(status_code=500, detail=f"Failed to pull model: {result.stderr}")
        return {"status": "success"}
    except Exception as e:
        log.error(f"Failed to pull ollama model: {e}")
        raise HTTPException(status_code=500, detail=str(e))
