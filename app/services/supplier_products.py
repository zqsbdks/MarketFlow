"""供应商商品目录的业务逻辑。"""

from fastapi import HTTPException
from fastapi import status as http_status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.auth import get_employee_by_id
from app.crud.supplier_products import (
    create_supplier_product,
    get_all_supplier_products,
    get_supplier_product_by_id,
    get_supplier_product_by_name,
    update_supplier_product,
    update_supplier_product_status,
)
from app.crud.suppliers import get_supplier_by_id
from app.models.enums import EmployeeRole
from app.models.supplier_product import SupplierProduct
from app.schemas.supplier_products_requests import (
    SupplierProductCreateRequest,
    SupplierProductUpdateRequest,
)
from app.schemas.supplier_products_responses import (
    SupplierProductItemResponse,
    SupplierProductListResponse,
)


def _build_supplier_product_response(
    supplier_product: SupplierProduct,
) -> SupplierProductItemResponse:
    """把目录商品及其关联的供应商名称组装成响应模型。"""

    return SupplierProductItemResponse(
        id=supplier_product.id,
        supplier_id=supplier_product.supplier_id,
        supplier_name=supplier_product.supplier.name,
        name=supplier_product.name,
        unit_cost=supplier_product.unit_cost,
        shelf_life_days=supplier_product.shelf_life_days,
        is_active=supplier_product.is_active,
        created_at=supplier_product.created_at,
        updated_at=supplier_product.updated_at,
    )


async def get_supplier_products_list_service(
    page: int,
    page_size: int,
    supplier_id: int | None,
    keyword: str | None,
    is_active: bool | None,
    current_employee_id: int,
    db: AsyncSession,
) -> SupplierProductListResponse:
    """验证当前员工状态，并返回筛选和分页后的供应商商品列表。"""

    current_employee = await get_employee_by_id(employee_id=current_employee_id, db=db)
    if current_employee is None:
        raise HTTPException(
            status_code=http_status.HTTP_401_UNAUTHORIZED,
            detail="当前登录员工不存在",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not current_employee.is_active:
        raise HTTPException(status_code=http_status.HTTP_403_FORBIDDEN, detail="账号已停用")
    if current_employee.must_change_password:
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="请先修改初始密码",
        )

    offset = (page - 1) * page_size
    supplier_products, total = await get_all_supplier_products(
        offset=offset,
        page_size=page_size,
        supplier_id=supplier_id,
        keyword=keyword,
        is_active=is_active,
        db=db,
    )

    items: list[SupplierProductItemResponse] = []
    for supplier_product in supplier_products:
        items.append(_build_supplier_product_response(supplier_product))

    return SupplierProductListResponse(
        items=items,
        page=page,
        page_size=page_size,
        total=total,
        total_pages=(total + page_size - 1) // page_size,
    )


async def get_supplier_product_detail_service(
    supplier_product_id: int,
    current_employee_id: int,
    db: AsyncSession,
) -> SupplierProductItemResponse:
    """验证当前员工状态，并返回指定供应商商品详情。"""

    current_employee = await get_employee_by_id(employee_id=current_employee_id, db=db)
    if current_employee is None:
        raise HTTPException(
            status_code=http_status.HTTP_401_UNAUTHORIZED,
            detail="当前登录员工不存在",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not current_employee.is_active:
        raise HTTPException(status_code=http_status.HTTP_403_FORBIDDEN, detail="账号已停用")
    if current_employee.must_change_password:
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="请先修改初始密码",
        )

    supplier_product = await get_supplier_product_by_id(
        supplier_product_id=supplier_product_id,
        db=db,
    )
    if supplier_product is None:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail="供应商商品不存在",
        )
    return _build_supplier_product_response(supplier_product)


async def create_supplier_product_service(
    request: SupplierProductCreateRequest,
    current_employee_id: int,
    db: AsyncSession,
) -> SupplierProductItemResponse:
    """验证店长权限和供应商状态，并创建供应商商品。"""

    current_employee = await get_employee_by_id(employee_id=current_employee_id, db=db)
    if current_employee is None:
        raise HTTPException(
            status_code=http_status.HTTP_401_UNAUTHORIZED,
            detail="当前登录员工不存在",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not current_employee.is_active:
        raise HTTPException(status_code=http_status.HTTP_403_FORBIDDEN, detail="账号已停用")
    if current_employee.must_change_password:
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="请先修改初始密码",
        )
    if current_employee.role != EmployeeRole.STORE_MANAGER:
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="只有店长可以创建供应商商品",
        )

    supplier = await get_supplier_by_id(supplier_id=request.supplier_id, db=db)
    if supplier is None:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="供应商不存在")
    if not supplier.is_active:
        raise HTTPException(status_code=http_status.HTTP_400_BAD_REQUEST, detail="供应商已停用")

    same_name_product = await get_supplier_product_by_name(
        supplier_id=request.supplier_id,
        name=request.name,
        db=db,
    )
    if same_name_product is not None:
        raise HTTPException(
            status_code=http_status.HTTP_409_CONFLICT,
            detail="该供应商已存在同名商品",
        )

    try:
        created_product = await create_supplier_product(
            supplier_id=request.supplier_id,
            name=request.name,
            unit_cost=request.unit_cost,
            shelf_life_days=request.shelf_life_days,
            db=db,
        )
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=http_status.HTTP_409_CONFLICT,
            detail="该供应商已存在同名商品",
        ) from exc

    # 重新查询以加载supplier关系，并取得数据库自动生成的时间字段。
    saved_product = await get_supplier_product_by_id(
        supplier_product_id=created_product.id,
        db=db,
    )
    if saved_product is None:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="供应商商品不存在")
    return _build_supplier_product_response(saved_product)


async def update_supplier_product_status_service(
    supplier_product_id: int,
    is_active: bool,
    current_employee_id: int,
    db: AsyncSession,
) -> SupplierProductItemResponse:
    """验证店长权限，并修改供应商商品的供应状态。"""

    current_employee = await get_employee_by_id(employee_id=current_employee_id, db=db)
    if current_employee is None:
        raise HTTPException(
            status_code=http_status.HTTP_401_UNAUTHORIZED,
            detail="当前登录员工不存在",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not current_employee.is_active:
        raise HTTPException(status_code=http_status.HTTP_403_FORBIDDEN, detail="账号已停用")
    if current_employee.must_change_password:
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="请先修改初始密码",
        )
    if current_employee.role != EmployeeRole.STORE_MANAGER:
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="只有店长可以修改供应商商品状态",
        )

    supplier_product = await get_supplier_product_by_id(
        supplier_product_id=supplier_product_id,
        db=db,
    )
    if supplier_product is None:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="供应商商品不存在")
    # 供应商停用时，不能单独重新启用它目录下的商品。
    if is_active and not supplier_product.supplier.is_active:
        raise HTTPException(status_code=http_status.HTTP_400_BAD_REQUEST, detail="供应商已停用")

    await update_supplier_product_status(
        supplier_product_id=supplier_product_id,
        is_active=is_active,
        db=db,
    )
    await db.commit()
    updated_product = await get_supplier_product_by_id(
        supplier_product_id=supplier_product_id,
        db=db,
    )
    if updated_product is None:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="供应商商品不存在")
    return _build_supplier_product_response(updated_product)


async def update_supplier_product_service(
    supplier_product_id: int,
    request: SupplierProductUpdateRequest,
    current_employee_id: int,
    db: AsyncSession,
) -> SupplierProductItemResponse:
    """验证店长权限，按需修改供应商商品详情。"""

    current_employee = await get_employee_by_id(employee_id=current_employee_id, db=db)
    if current_employee is None:
        raise HTTPException(
            status_code=http_status.HTTP_401_UNAUTHORIZED,
            detail="当前登录员工不存在",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not current_employee.is_active:
        raise HTTPException(status_code=http_status.HTTP_403_FORBIDDEN, detail="账号已停用")
    if current_employee.must_change_password:
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="请先修改初始密码",
        )
    if current_employee.role != EmployeeRole.STORE_MANAGER:
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="只有店长可以修改供应商商品详情",
        )

    existing_product = await get_supplier_product_by_id(
        supplier_product_id=supplier_product_id,
        db=db,
    )
    if existing_product is None:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="供应商商品不存在")

    update_data = request.model_dump(exclude_unset=True)
    if not update_data:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail="至少传入一个需要修改的字段",
        )
    if update_data.get("name", existing_product.name) is None:
        raise HTTPException(status_code=http_status.HTTP_400_BAD_REQUEST, detail="商品名称不能为空")
    if update_data.get("unit_cost", existing_product.unit_cost) is None:
        raise HTTPException(status_code=http_status.HTTP_400_BAD_REQUEST, detail="进货单价不能为空")

    new_name = update_data.get("name")
    if isinstance(new_name, str):
        same_name_product = await get_supplier_product_by_name(
            supplier_id=existing_product.supplier_id,
            name=new_name,
            excluded_supplier_product_id=supplier_product_id,
            db=db,
        )
        if same_name_product is not None:
            raise HTTPException(
                status_code=http_status.HTTP_409_CONFLICT,
                detail="该供应商已存在同名商品",
            )

    try:
        await update_supplier_product(
            supplier_product_id=supplier_product_id,
            update_data=update_data,
            db=db,
        )
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=http_status.HTTP_409_CONFLICT,
            detail="该供应商已存在同名商品",
        ) from exc

    updated_product = await get_supplier_product_by_id(
        supplier_product_id=supplier_product_id,
        db=db,
    )
    if updated_product is None:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="供应商商品不存在")
    return _build_supplier_product_response(updated_product)


__all__ = [
    "create_supplier_product_service",
    "get_supplier_product_detail_service",
    "get_supplier_products_list_service",
    "update_supplier_product_service",
    "update_supplier_product_status_service",
]
