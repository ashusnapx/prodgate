from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Project
from app.services import documents
from app.services.errors import Conflict, NotFound


def get_project(db: Session, org_id: str, code: str) -> Project:
    project = db.scalar(select(Project).where(Project.org_id == org_id, Project.code == code))
    if project is None:
        raise NotFound("project", code)
    return project


def list_projects(db: Session, org_id: str) -> list[Project]:
    return list(db.scalars(select(Project).where(Project.org_id == org_id).order_by(Project.name)))


def create_project(db: Session, org_id: str, code: str, name: str) -> Project:
    if db.scalar(select(Project.id).where(Project.org_id == org_id, Project.code == code)):
        raise Conflict(f"project code {code!r} is taken")
    project = Project(org_id=org_id, code=code, name=name)
    db.add(project)
    db.commit()
    return project


def rename_project(db: Session, org_id: str, code: str, new_code: str, new_name: str) -> Project:
    """Change a project's code and name; its documents move with it."""
    project = get_project(db, org_id, code)
    if new_code != code and db.scalar(select(Project.id).where(Project.org_id == org_id, Project.code == new_code)):
        raise Conflict(f"project code {new_code!r} is taken")

    for doc in documents.list_documents(db, org_id, code):
        doc.project_code = new_code
    project.code = new_code
    project.name = new_name
    db.commit()
    return project
