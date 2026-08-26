"""
Discovery Service FastAPI Application

REST API for strategy discovery.
"""

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
import logging

from shared.models import (
    DiscoveryRequest,
    DiscoveryResponse,
    JobStatus,
)

logger = logging.getLogger(__name__)

app = FastAPI(
    title="StrategyOps Discovery Service",
    description="Strategy discovery via vectorbt backtesting",
    version="2.0.0"
)

# In-memory job store (temporary, will use database later)
job_store = {}


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "discovery"}


@app.post("/api/v1/discovery/start")
async def start_discovery(request: DiscoveryRequest) -> DiscoveryResponse:
    """
    Start strategy discovery job.
    
    Args:
        request: DiscoveryRequest with symbol, timeframe, session, entry_floors
    
    Returns:
        DiscoveryResponse with job_id and initial status
    """
    logger.info(f"Starting discovery: {request.symbol}/{request.session}/{request.timeframe}")
    
    # Create job
    job_id = request.job_id
    
    response = DiscoveryResponse(
        job_id=job_id,
        status=JobStatus.RUNNING,
        symbol=request.symbol,
        session=request.session,
    )
    
    # Store job
    job_store[job_id] = {
        'request': request,
        'response': response,
        'status': JobStatus.RUNNING
    }
    
    return response


@app.get("/api/v1/discovery/{job_id}/status")
async def get_discovery_status(job_id: str) -> DiscoveryResponse:
    """
    Get discovery job status.
    
    Args:
        job_id: Job ID
    
    Returns:
        Current job status and results
    """
    if job_id not in job_store:
        raise HTTPException(status_code=404, detail="Job not found")
    
    job = job_store[job_id]
    return job['response']


@app.get("/api/v1/discovery/{job_id}/results")
async def get_discovery_results(job_id: str) -> JSONResponse:
    """
    Get discovery job results.
    
    Args:
        job_id: Job ID
    
    Returns:
        Discovered strategies
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
            "strategies": response.discovered_strategies
        }
    )


@app.get("/api/v1/discovery/strategies")
async def list_available_strategies() -> JSONResponse:
    """List all available strategies for discovery."""
    strategies = [
        {"name": "RSI14", "type": "momentum", "description": "RSI momentum indicator"},
        {"name": "RSI9", "type": "momentum", "description": "Fast RSI momentum indicator"},
        {"name": "Stochastic14", "type": "momentum", "description": "Stochastic oscillator"},
        {"name": "OsMA_Confluence", "type": "confluence", "description": "OsMA + MA confluence"},
    ]
    return JSONResponse(status_code=200, content={"strategies": strategies})


@app.post("/api/v1/discovery/{job_id}/cancel")
async def cancel_discovery(job_id: str) -> JSONResponse:
    """Cancel a running discovery job."""
    if job_id not in job_store:
        raise HTTPException(status_code=404, detail="Job not found")
    
    job = job_store[job_id]
    job['status'] = JobStatus.CANCELLED
    job['response'].status = JobStatus.CANCELLED
    
    return JSONResponse(status_code=200, content={"message": "Job cancelled"})


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
