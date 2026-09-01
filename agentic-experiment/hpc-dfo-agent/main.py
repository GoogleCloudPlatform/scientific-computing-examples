from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from shared.registry import Registry
from shared.logger import get_logger

logger = get_logger("SkillHost")

app = FastAPI(
    title="HPC Agent Skills Foundation",
    description="A central host dynamically serving multiple independent ADK skills.",
    version="0.1.0"
)

# Initialize registry and load all skills at startup
registry = Registry()

class InvokeRequest(BaseModel):
    message: str
    session_id: str | None = None

@app.get("/")
def read_root():
    return {"status": "ok", "skills": list(registry.get_all_agents().keys())}

@app.post("/skills/{skill_name}/invoke")
async def invoke_skill(skill_name: str, request: InvokeRequest):
    agent = registry.get_agent(skill_name)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Skill '{skill_name}' not found in registry.")
    
    logger.info(f"Invoking skill {skill_name} with message: {request.message}")
    
    # Simple direct ADK Agent invocation (stateless by default in this prototype)
    try:
        # Note: In a production setup with ADK, you would bind a session
        # and execute asynchronously.
        response = agent.run(request.message)
        return {"response": response.text}
    except Exception as e:
        logger.error(f"Error invoking skill {skill_name}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
