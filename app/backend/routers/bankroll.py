"""Bankroll bookkeeping endpoints (E9.17).

GET  /users/bankroll               — books, events, computed growth
PUT  /users/bankroll/books/{book}  — set a book's current balance
POST /users/bankroll/events        — record a deposit or withdrawal
DELETE /users/bankroll/books/{book} — remove a book (events preserved)

Growth math is honest: deposits and withdrawals are netted out so the
growth % reflects only betting performance, not cash movement.
"""

from __future__ import annotations

import logging
from datetime import date as _date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.backend.dependencies import get_user_id
from app.backend.services.dynamo import (
    add_bankroll_event,
    delete_bankroll_event,
    get_bankroll,
    reassign_book,
    remove_book,
    upsert_book_balance,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/users", tags=["bankroll"])

VALID_BOOKS = frozenset([
    "BetMGM", "Caesars", "FanDuel", "DraftKings",
    "Fanatics", "Bovada", "Pinnacle", "Unspecified",
])


class BookBalanceUpdate(BaseModel):
    current_balance: float = Field(..., ge=0)


class BankrollEventRequest(BaseModel):
    book: str
    type: str = Field(..., pattern="^(deposit|withdrawal)$")
    amount: float = Field(..., gt=0)
    date: str = Field(..., description="ISO date YYYY-MM-DD")


class ReassignBookRequest(BaseModel):
    to_book: str


def _validate_book(book: str) -> None:
    if book not in VALID_BOOKS:
        raise HTTPException(
            status_code=422,
            detail=f"Unknown sportsbook '{book}'. Valid choices: {sorted(VALID_BOOKS)}",
        )


def _validate_date(date_str: str) -> None:
    try:
        _date.fromisoformat(date_str)
    except ValueError:
        raise HTTPException(status_code=422, detail="date must be YYYY-MM-DD")


@router.get("/bankroll")
def get_bankroll_route(user_id: str = Depends(get_user_id)):
    try:
        return get_bankroll(user_id)
    except Exception as exc:
        logger.exception("get_bankroll failed for %s", user_id)
        raise HTTPException(status_code=503, detail="Bankroll unavailable") from exc


@router.put("/bankroll/books/{book}")
def upsert_balance(
    book: str,
    body: BookBalanceUpdate,
    user_id: str = Depends(get_user_id),
):
    _validate_book(book)
    try:
        return upsert_book_balance(user_id, book, body.current_balance)
    except Exception as exc:
        logger.exception("upsert_book_balance failed for %s", user_id)
        raise HTTPException(status_code=503, detail="Could not save balance") from exc


@router.post("/bankroll/events")
def add_event(body: BankrollEventRequest, user_id: str = Depends(get_user_id)):
    _validate_book(body.book)
    _validate_date(body.date)
    try:
        return add_bankroll_event(user_id, body.book, body.type, body.amount, body.date)
    except Exception as exc:
        logger.exception("add_bankroll_event failed for %s", user_id)
        raise HTTPException(status_code=503, detail="Could not record event") from exc


@router.delete("/bankroll/books/{book}")
def delete_book(book: str, user_id: str = Depends(get_user_id)):
    try:
        return remove_book(user_id, book)
    except Exception as exc:
        logger.exception("remove_book failed for %s", user_id)
        raise HTTPException(status_code=503, detail="Could not remove book") from exc


@router.delete("/bankroll/events/{event_id}")
def delete_event(event_id: str, user_id: str = Depends(get_user_id)):
    try:
        return delete_bankroll_event(user_id, event_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("delete_bankroll_event failed for %s", user_id)
        raise HTTPException(status_code=503, detail="Could not delete event") from exc


@router.patch("/bankroll/books/{book}/reassign")
def reassign_book_route(
    book: str,
    body: ReassignBookRequest,
    user_id: str = Depends(get_user_id),
):
    _validate_book(book)
    _validate_book(body.to_book)
    if book == body.to_book:
        raise HTTPException(status_code=422, detail="from_book and to_book must be different")
    try:
        return reassign_book(user_id, book, body.to_book)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("reassign_book failed for %s", user_id)
        raise HTTPException(status_code=503, detail="Could not reassign book") from exc
