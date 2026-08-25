"""
Validation Service FastAPI Application

REST API for strategy validation.
"""

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
import logging

from shared.models import (
    ValidationRequest,
    ValidationResponse,
    JobStatus,
)

logger = logging.getLogger(__name__)

app = FastAPI(
    title="StrategyOps Validation Service",
    description="Pre-deployment strategy validation",
    version="2.0.0"
)

job_store = {}


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "validation"}


@app.post("/api/v1/validation/start")
async def start_validation(request: ValidationRequest) -> ValidationResponse:
    """
    Start strategy validation job.
    
    Args:
        request: ValidationRequest with strategy metrics
    
    Returns:
        ValidationResponse with job_id and status
    """
    logger.info(
        f"Starting validation: {request.symbol}/"
        f"{request.strategy_name}/{request.session}"
    )
    
    job_id = request.job_id
    
    response = ValidationResponse(
        job_id=job_id,
        status=JobStatus.RUNNING,
        symbol=request.symbol,
        strategy_name=request.strategy_name,
        is_valid=None,
        validation_results={}
    )
    
    job_store[job_id] = {
        'request': request,
        'response': response,
        'status': JobStatus.RUNNING
    }
    
    return response


@app.get("/api/v1/validation/{job_id}/status")
async def get_validation_status(job_id: str) -> ValidationResponse:
    """
    Get validation job status.
    
    Args:
        job_id: Job ID
    
    Returns:
        Current job status and results
    """
    if job_id not in job_store:
        raise HTTPException(status_code=404, detail="Job not found")
    
    job = job_store[job_id]
    return job['response']


@app.get("/api/v1/validation/{job_id}/results")
async def get_validation_results(job_id: str) -> JSONResponse:
    """
    Get validation job results.
    
    Args:
        job_id: Job ID
    
    Returns:
        Validation results with pass/fail status and rules
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
            "is_valid": response.is_valid,
            "results": response.validation_results
        }
    )


@app.get("/api/v1/validation/rules")
async def get_validation_rules() -> JSONResponse:
    """Get validation rules and thresholds."""
    return JSONResponse(
        status_code=200,
        content={
            "validation_rules": {
                "min_profit_factor": 1.3,
                "min_win_rate": 0.45,
                "min_sharpe": 1.0,
                "min_trades": 10,
                "max_consecutive_losses": 5,
                "min_edge_percentage": 2.0
            }
        }
    )


@app.post("/api/v1/validation/{job_id}/cancel")
async def cancel_validation(job_id: str) -> JSONResponse:
    """Cancel a running validation job."""
    if job_id not in job_store:
        raise HTTPException(status_code=404, detail="Job not found")
    
    job = job_store[job_id]
    job['status'] = JobStatus.CANCELLED
    job['response'].status = JobStatus.CANCELLED
    
    return JSONResponse(status_code=200, content={"message": "Job cancelled"})


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8003)
