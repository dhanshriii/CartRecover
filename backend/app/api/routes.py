
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.entities import Cart
from app.services.recovery_engine import evaluate_recovery
from app.services.campaign_service import schedule_recovery
from app.services.attribution_service import attribute_order

from app.api.schemas import (
    RecoveryEvaluateRequest,
    CampaignScheduleRequest,
    AttributionRequest,
)


router = APIRouter(prefix="/api", tags=["Cart Recovery"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.post("/recovery/evaluate")
def recovery_evaluate(
    request: RecoveryEvaluateRequest,
    db: Session = Depends(get_db),
):
    cart = db.query(Cart).filter(
        Cart.cart_id == request.cart_id
    ).first()

    if cart is None:
        raise HTTPException(
            status_code=404,
            detail="Cart not found",
        )

    evaluated_at = request.evaluated_at or datetime.now()

    try:
        return evaluate_recovery(
            db=db,
            cart=cart,
            channel=request.channel,
            evaluated_at=evaluated_at,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        )


@router.post("/campaigns/schedule")
def campaign_schedule(
    request: CampaignScheduleRequest,
    db: Session = Depends(get_db),
):
    cart = db.query(Cart).filter(
        Cart.cart_id == request.cart_id
    ).first()

    if cart is None:
        raise HTTPException(
            status_code=404,
            detail="Cart not found",
        )

    evaluated_at = request.evaluated_at or datetime.now()

    try:
        return schedule_recovery(
            db=db,
            cart=cart,
            channel=request.channel,
            evaluated_at=evaluated_at,
            send_id=request.send_id,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        )


@router.post("/attribution")
def create_attribution(
    request: AttributionRequest,
    db: Session = Depends(get_db),
):
    try:
        result = attribute_order(
            db=db,
            order_id=request.order_id,
            attribution_id=request.attribution_id,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        )

    if result["status"] == "NOT_FOUND":
        raise HTTPException(
            status_code=404,
            detail=result["reason"],
        )

    return result
