from fastapi import APIRouter

router = APIRouter()


@router.get("/ping")
def ping_market() -> dict[str, str]:
    return {"module": "market", "status": "ready"}
