"""
Optimization Service FastAPI Application

REST API for floor value optimization.
"""

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
import logging

from shared.models import (
    OptimizationRequest,
    OptimizationResponse,
    JobStatus,
)

logger = logging.getLogger(__name__)

app = FastAPI(
    title="StrategyOps Optimization Service",
    description="Floor value optimization via Optuna",
    version="2.0.0"
)

# In-memory job store
job_store = {}


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "optimization"}


@app.post("/api/v1/optimization/start")
async def start_optimization(request: OptimizationRequest) -> OptimizationResponse:
    """
    Start floor optimization job.
    
    Args:
        request: OptimizationRequest with strategy, symbol, session, etc.
    
    Returns:
        OptimizationResponse with job_id and status
    """
    logger.info(
        f"Starting optimization: {request.symbol}/{request.strategy_name}/"
        f"{request.session}"
    )
    
    job_id = request.job_id
    
    response = OptimizationResponse(
        job_id=job_id,
        status=JobStatus.RUNNING,
        symbol=request.symbol,
        strategy_name=request.strategy_name,
        best_floor=None,
        trials=[],
    )
    
    job_store[job_id] = {
        'request': request,
        'response': response,
        'status': JobStatus.RUNNING
    }
    
    return response


@app.get("/api/v1/optimization/{job_id}/status")
async def get_optimization_status(job_id: str) -> OptimizationResponse:
    """
    Get optimization job status.
    
    Args:
        job_id: Job ID
    
    Returns:
        Current job status and results
    """
    if job_id not in job_store:
        raise HTTPException(status_code=404, detail="Job not found")
    
    job = job_store[job_id]
    return job['response']


@app.get("/api/v1/optimization/{job_id}/results")
async def get_optimization_results(job_id: str) -> JSONResponse:
    """
    Get optimization job results.
    
    Args:
        job_id: Job ID
    
    Returns:
        Optimization results with best floor and trial data
    """
    if job_id not in job_store:
        raise HTTPException(status_code=404, detail="Job not found")
    
    job = job_store[job_id]
    response = job['response']
    
    if response.status != JobStatus.COMPLETED:
        return JSONResponse(
            status_code=202,
            content={"status": response.status, "message": "Job still running"}
        )
    
    return JSONResponse(
        status_code=200,
        content={
            "job_id": response.job_id,
            "status": response.status,
            "best_floor": response.best_floor,
            "trials": response.trials
        }
    )


@app.post("/api/v1/optimization/{job_id}/cancel")
async def cancel_optimization(job_id: str) -> JSONResponse:
    """Cancel a running optimization job."""
    if job_id not in job_store:
        raise HTTPException(status_code=404, detail="Job not found")
    
    job = job_store[job_id]
    job['status'] = JobStatus.CANCELLED
    job['response'].status = JobStatus.CANCELLED
    
    return JSONResponse(status_code=200, content={"message": "Job cancelled"})


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8002)
