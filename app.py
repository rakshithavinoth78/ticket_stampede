
import sqlite3
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

DATABASE = "tickets.db"
DEFAULT_TICKETS = 100


def get_connection():
    connection = sqlite3.connect(DATABASE, timeout=30)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA busy_timeout = 30000")
    return connection


def initialize_database():
    connection = get_connection()

    connection.execute("""
        CREATE TABLE IF NOT EXISTS sale (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            capacity INTEGER NOT NULL
        )
    """)

    connection.execute("""
        CREATE TABLE IF NOT EXISTS purchases (
            ticket_number INTEGER PRIMARY KEY,
            user_id TEXT NOT NULL,
            request_id TEXT NOT NULL UNIQUE
        )
    """)

    connection.execute("""
        INSERT OR IGNORE INTO sale (id, capacity)
        VALUES (1, ?)
    """, (DEFAULT_TICKETS,))

    connection.commit()
    connection.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    initialize_database()
    yield


app = FastAPI(
    title="Ticket Stampede API",
    description="A concurrency-safe ticket selling service",
    lifespan=lifespan
)


class ResetRequest(BaseModel):
    ticket_count: int


class BuyRequest(BaseModel):
    user_id: str
    request_id: str


@app.post("/reset")
def reset_tickets(request: ResetRequest):
    if request.ticket_count < 0:
        raise HTTPException(
            status_code=400,
            detail="Ticket count cannot be negative"
        )

    connection = get_connection()

    try:
        connection.execute("BEGIN IMMEDIATE")

        connection.execute("DELETE FROM purchases")
        connection.execute(
            "UPDATE sale SET capacity = ? WHERE id = 1",
            (request.ticket_count,)
        )

        connection.commit()

        return {
            "message": "Ticket sale reset successfully",
            "ticket_count": request.ticket_count
        }

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()


@app.post("/buy")
def buy_ticket(request: BuyRequest):
    if not request.user_id.strip() or not request.request_id.strip():
        raise HTTPException(
            status_code=400,
            detail="user_id and request_id cannot be empty"
        )

    connection = get_connection()

    try:
        # Lock the database for this transaction so concurrent
        # buyers cannot allocate the same ticket number.
        connection.execute("BEGIN IMMEDIATE")

        # A repeated request ID must return its original ticket.
        existing = connection.execute(
            """
            SELECT ticket_number, user_id
            FROM purchases
            WHERE request_id = ?
            """,
            (request.request_id,)
        ).fetchone()

        if existing:
            connection.commit()
            return {
                "status": "success",
                "ticket_number": existing["ticket_number"],
                "user_id": existing["user_id"],
                "request_id": request.request_id,
                "duplicate_request": True
            }

        sale = connection.execute(
            "SELECT capacity FROM sale WHERE id = 1"
        ).fetchone()

        sold = connection.execute(
            "SELECT COUNT(*) AS total FROM purchases"
        ).fetchone()["total"]

        if sold >= sale["capacity"]:
            connection.commit()
            return {
                "status": "sold_out",
                "message": "No tickets remaining",
                "request_id": request.request_id
            }

        ticket_number = sold + 1

        connection.execute(
            """
            INSERT INTO purchases
            (ticket_number, user_id, request_id)
            VALUES (?, ?, ?)
            """,
            (ticket_number, request.user_id, request.request_id)
        )

        connection.commit()

        return {
            "status": "success",
            "ticket_number": ticket_number,
            "user_id": request.user_id,
            "request_id": request.request_id,
            "duplicate_request": False
        }

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()


@app.get("/status")
def get_status():
    connection = get_connection()

    try:
        sale = connection.execute(
            "SELECT capacity FROM sale WHERE id = 1"
        ).fetchone()

        purchases = connection.execute(
            """
            SELECT ticket_number, user_id, request_id
            FROM purchases
            ORDER BY ticket_number
            """
        ).fetchall()

        sold = len(purchases)

        user_tickets = {}
        for purchase in purchases:
            user_tickets.setdefault(
                purchase["user_id"], []
            ).append(purchase["ticket_number"])

        return {
            "capacity": sale["capacity"],
            "sold": sold,
            "remaining": sale["capacity"] - sold,
            "user_tickets": user_tickets,
            "purchases": [
                {
                    "ticket_number": p["ticket_number"],
                    "user_id": p["user_id"],
                    "request_id": p["request_id"]
                }
                for p in purchases
            ]
        }

    finally:
        connection.close()