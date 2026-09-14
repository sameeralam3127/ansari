"""The fleet's cached view of what each repo's manifest says.

One binding per template attached to a project's repo. A client that has run
`ansari check` reports the repo's whole set at once; the fleet listing then
answers "who is behind, and on what?" without cloning anything. The manifest
committed in the repo stays authoritative -- this is a cache of it.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ansari.api.db import get_db
from ansari.api.models import Project, TemplateBinding
from ansari.api.pagination import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE
from ansari.api.schemas import TemplateBindingRead, TemplateBindingWrite

router = APIRouter(tags=["template-bindings"])


def _project_or_404(db: Session, project_id: uuid.UUID) -> Project:
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="project not found")
    return project


@router.put("/projects/{project_id}/template-bindings", response_model=list[TemplateBindingRead])
def replace_template_bindings(
    project_id: uuid.UUID,
    payload: list[TemplateBindingWrite],
    db: Session = Depends(get_db),
) -> list[TemplateBinding]:
    """Replace a project's bindings with the set its manifest currently lists.

    The whole set at once, in manifest order, because that's what a manifest is:
    a partial update could leave a template the repo has since dropped. Applies
    the manifest's own invariant, that no file has two owners.
    """
    project = _project_or_404(db, project_id)

    owners: dict[str, str] = {}
    conflicts: set[str] = set()
    for binding in payload:
        for path in binding.files:
            if path in owners:
                conflicts.add(path)
            owners[path] = binding.template
    if conflicts:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"files claimed by more than one template: {sorted(conflicts)}",
        )

    project.template_bindings.clear()
    # Delete the old rows before inserting the new ones: a single flush would
    # insert first and collide on (project_id, position).
    db.flush()
    for position, binding in enumerate(payload):
        project.template_bindings.append(TemplateBinding(position=position, **binding.model_dump()))
    db.commit()
    return _bindings_for(db, project_id, DEFAULT_PAGE_SIZE, 0)


@router.get("/projects/{project_id}/template-bindings", response_model=list[TemplateBindingRead])
def list_project_template_bindings(
    project_id: uuid.UUID,
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = DEFAULT_PAGE_SIZE,
    offset: Annotated[int, Query(ge=0)] = 0,
    db: Session = Depends(get_db),
) -> list[TemplateBinding]:
    _project_or_404(db, project_id)
    return _bindings_for(db, project_id, limit, offset)


@router.get("/template-bindings", response_model=list[TemplateBindingRead])
def list_template_bindings(
    template: str | None = None,
    behind: bool | None = None,
    edited: bool | None = None,
    unresolved: bool | None = None,
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = DEFAULT_PAGE_SIZE,
    offset: Annotated[int, Query(ge=0)] = 0,
    db: Session = Depends(get_db),
) -> list[TemplateBinding]:
    """Bindings across every project: `?template=python-service&behind=true`."""
    stmt = select(TemplateBinding)
    if template is not None:
        stmt = stmt.where(TemplateBinding.template == template)
    if behind is not None:
        stmt = stmt.where(TemplateBinding.behind == behind)
    if edited is not None:
        stmt = stmt.where(TemplateBinding.edited == edited)
    if unresolved is not None:
        stmt = stmt.where(TemplateBinding.unresolved == unresolved)
    stmt = (
        stmt.order_by(
            TemplateBinding.template, TemplateBinding.project_id, TemplateBinding.position
        )
        .limit(limit)
        .offset(offset)
    )
    return list(db.scalars(stmt))


def _bindings_for(
    db: Session, project_id: uuid.UUID, limit: int, offset: int
) -> list[TemplateBinding]:
    stmt = (
        select(TemplateBinding)
        .where(TemplateBinding.project_id == project_id)
        .order_by(TemplateBinding.position)
        .limit(limit)
        .offset(offset)
    )
    return list(db.scalars(stmt))
