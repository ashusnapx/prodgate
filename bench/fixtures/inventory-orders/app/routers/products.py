from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.deps import get_session, require_staff
from app.models import Product
from app.schemas import ProductIn, ProductOut
from app.services.orders import NotFound

router = APIRouter(prefix="/products", tags=["products"])


def _product(session: Session, product_id: int) -> Product:
    product = session.get(Product, product_id)
    if product is None:
        raise NotFound(f"product {product_id}")
    return product


@router.get("/{product_id}", response_model=ProductOut)
def show_product(product_id: int, session: Session = Depends(get_session)):
    return _product(session, product_id)


@router.post("", status_code=201, response_model=ProductOut, dependencies=[Depends(require_staff)])
def create_product(body: ProductIn, session: Session = Depends(get_session)):
    product = Product(**body.model_dump())
    session.add(product)
    session.commit()
    return product
