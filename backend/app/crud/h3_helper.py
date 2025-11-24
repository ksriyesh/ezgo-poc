"""Helper functions for H3 operations in CRUD."""
from typing import Dict, List
from uuid import UUID
from sqlalchemy.orm import Session
from app.models.h3_cover import H3Cover, OwnerKind
from app.models.h3_compact import H3Compact


def get_h3_coverage(
    db: Session,
    owner_kind: OwnerKind,
    owner_id: UUID,
    resolutions: List[int] = None
) -> Dict[int, Dict]:
    """
    Get H3 coverage for an owner (service_area or service_zone) at specified resolutions.
    
    Returns a dictionary with resolution as key and coverage data as value.
    """
    if resolutions is None:
        resolutions = [7, 8, 9, 10]  # Default resolutions
    
    coverage = {}
    
    for resolution in resolutions:
        # Get H3 covers for this resolution
        covers = db.query(H3Cover).filter(
            H3Cover.owner_kind == owner_kind,
            H3Cover.owner_id == owner_id,
            H3Cover.resolution == resolution
        ).all()
        
        # Get compacted version if exists
        compact = db.query(H3Compact).filter(
            H3Compact.owner_kind == owner_kind,
            H3Compact.owner_id == owner_id,
            H3Compact.resolution == resolution
        ).first()
        
        if covers:
            cells = [cover.cell for cover in covers]
            coverage[resolution] = {
                "resolution": resolution,
                "cells": cells,
                "cell_count": len(cells),
                "compacted_cells": compact.cells_compact if compact else None
            }
    
    return coverage

