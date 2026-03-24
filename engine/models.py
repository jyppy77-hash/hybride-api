from typing import Literal

from pydantic import BaseModel, Field


class GenerateRequest(BaseModel):
    """Request schema for grid generation endpoints."""

    n: int = Field(default=5, ge=1, le=20, description="Number of grids to generate (1-20)")
    mode: Literal["conservative", "balanced", "recent"] = Field(
        default="balanced", description="Generation mode"
    )
