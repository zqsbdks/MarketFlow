"""商品查询业务逻辑。"""

from fastapi import HTTPException
from fastapi import status as http_status
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.auth import get_employee_by_id
from app.crud.categories import get_category_by_id
from app.crud.operation_audit_logs import create_operation_audit_log
from app.crud.products import get_product_by_id, get_products_list, update_product
from app.models.enums import EmployeeRole, ProductStatus
from app.schemas.products_requests import ProductStatusUpdateRequest, UpdateProductRequest
from app.schemas.products_responses import (
    ItemResponse,
    ProductsItemResponse,
    ProductsListResponse,
)


# region 获取商品列表
async def get_products_list_service(
    page: int,
    page_size: int,
    keyword: str | None,
    department_id: int | None,
    category_id: int | None,
    status: ProductStatus | None,
    stock_consistent: bool | None,
    low_stock: bool | None,
    current_employee_id: int,
    db: AsyncSession,
) -> ProductsListResponse:
    """验证当前员工账号，并组装经过筛选和分页的商品列表。"""

    # Token 只能证明签发时员工存在；每次请求仍需检查账号的最新状态。
    current_employee = await get_employee_by_id(
        employee_id=current_employee_id,
        db=db,
    )
    if current_employee is None:
        raise HTTPException(
            status_code=http_status.HTTP_401_UNAUTHORIZED,
            detail="当前登录员工不存在",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not current_employee.is_active:
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="账号已停用",
        )

    if current_employee.must_change_password:
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="请先修改初始密码",
        )

    products, total = await get_products_list(
        page=page,
        page_size=page_size,
        keyword=keyword,
        department_id=department_id,
        category_id=category_id,
        status=status,
        stock_consistent=stock_consistent,
        low_stock=low_stock,
        db=db,
    )

    # 将 ORM 对象转换成明确的响应模型，避免返回未公开的商品字段。
    items: list[ProductsItemResponse] = []
    for product, inventory_summary in products:
        (
            total_stock_quantity,
            saleable_stock_quantity,
            near_expiry_stock_quantity,
            near_expiry_batch_count,
            expired_stock_quantity,
            expired_batch_count,
        ) = inventory_summary
        is_low_stock = (
            product.low_stock_threshold is not None
            and saleable_stock_quantity <= product.low_stock_threshold
        )
        items.append(
            ProductsItemResponse(
                id=product.id,
                product_no=product.product_no,
                name=product.name,
                department_name=product.department.name,
                category_name=product.category.name,
                purchase_price=product.purchase_price,
                sale_price=product.sale_price,
                stock_quantity=product.stock_quantity,
                batch_stock_quantity=total_stock_quantity,
                total_stock_quantity=total_stock_quantity,
                saleable_stock_quantity=saleable_stock_quantity,
                near_expiry_stock_quantity=near_expiry_stock_quantity,
                near_expiry_batch_count=near_expiry_batch_count,
                expired_stock_quantity=expired_stock_quantity,
                expired_batch_count=expired_batch_count,
                stock_difference=product.stock_quantity - total_stock_quantity,
                is_stock_consistent=product.stock_quantity == total_stock_quantity,
                low_stock_threshold=product.low_stock_threshold,
                is_low_stock=is_low_stock,
                status=product.status,
            )
        )

    total_pages = (total + page_size - 1) // page_size

    return ProductsListResponse(
        items=items,
        page=page,
        page_size=page_size,
        total=total,
        total_pages=total_pages,
    )


# endregion


# region 获取商品详情
async def get_product_detail_service(
    product_id: int,
    db: AsyncSession,
    current_employee_id: int,
) -> ItemResponse:
    """验证当前员工账号，并返回指定商品的详情。"""

    employee = await get_employee_by_id(
        employee_id=current_employee_id,
        db=db,
    )
    if employee is None:
        raise HTTPException(
            status_code=http_status.HTTP_401_UNAUTHORIZED,
            detail="当前登录员工不存在",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not employee.is_active:
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="账号已停用",
        )
    if employee.must_change_password:
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="请先修改初始密码",
        )
    product = await get_product_by_id(
        product_id=product_id,
        db=db,
    )
    if product is None:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail="商品不存在",
        )

    # ItemResponse 配置了 from_attributes=True，因此可以直接从 Product ORM
    # 对象读取同名属性；嵌套的 department 和 category 也会自动转换。
    return ItemResponse.model_validate(product)


# endregion


# region 修改商品状态
async def update_product_status_service(
    # product_id：准备修改销售状态的商品 ID。
    product_id: int,
    # request：前端提交的新商品销售状态。
    request: ProductStatusUpdateRequest,
    # current_employee_id：当前登录员工 ID，用于账号和权限校验。
    current_employee_id: int,
    # db：当前请求的异步数据库会话。
    db: AsyncSession,
) -> ItemResponse:
    """校验员工操作权限，修改商品销售状态并返回最新商品详情。"""

    # 第一步：查询当前登录员工，读取账号状态、角色和所属部门。
    employee = await get_employee_by_id(
        employee_id=current_employee_id,
        db=db,
    )
    if employee is None:
        raise HTTPException(
            status_code=http_status.HTTP_401_UNAUTHORIZED,
            detail="当前登录员工不存在",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 已停用账号不能修改商品状态。
    if not employee.is_active:
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="账号已停用",
        )

    # 使用初始密码的员工必须先修改密码。
    if employee.must_change_password:
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="请先修改初始密码",
        )

    # 第二步：只有店长和正式员工可以修改商品状态，契约工不能操作。
    if employee.role not in (
        EmployeeRole.STORE_MANAGER,
        EmployeeRole.REGULAR_EMPLOYEE,
    ):
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="只有店长或正式员工可以修改商品状态",
        )

    # 第三步：查询准备修改状态的商品。
    product = await get_product_by_id(
        product_id=product_id,
        db=db,
    )
    if product is None:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail="商品不存在",
        )

    # 第四步：店长可以操作所有商品，正式员工只能操作本部门商品。
    if (
        employee.role == EmployeeRole.REGULAR_EMPLOYEE
        and employee.department_id != product.department_id
    ):
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="正式员工只能修改自己所属部门的商品状态",
        )

    # 第五步：复用商品更新 CRUD，只把新的 status 写入数据库。
    previous_status = product.status
    updated_product = await update_product(
        product_id=product_id,
        update_data={"status": request.status},
        db=db,
    )

    await create_operation_audit_log(
        employee_id=employee.id,
        module="product",
        action="update_status",
        target_type="product",
        target_id=product.id,
        before_data={"status": previous_status},
        after_data={"status": request.status},
        reason=request.reason,
        db=db,
    )

    # 第六步：数据库更新成功后提交事务。
    await db.commit()

    # 第七步：返回与商品详情、商品资料修改接口相同的响应结构。
    return ItemResponse.model_validate(updated_product)


# endregion


# region 修改商品详情
async def update_product_service(
    # product_id：准备修改的商品 ID。
    product_id: int,
    # request：前端实际提交的可选修改字段。
    request: UpdateProductRequest,
    # current_employee_id：当前登录员工 ID，用于账号和权限校验。
    current_employee_id: int,
    # db：当前请求的异步数据库会话。
    db: AsyncSession,
) -> ItemResponse:
    """校验当前员工和修改内容，更新商品并返回最新详情。"""

    # 第一步：查询当前登录员工，读取账号状态、角色和所属部门。
    employee = await get_employee_by_id(
        employee_id=current_employee_id,
        db=db,
    )
    # Token 中虽然保存了员工 ID，但员工账号之后可能已经被删除。
    if employee is None:
        raise HTTPException(
            status_code=http_status.HTTP_401_UNAUTHORIZED,
            detail="当前登录员工不存在",
            headers={"WWW-Authenticate": "Bearer"},
        )
    # 已停用账号不能继续操作系统业务。
    if not employee.is_active:
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="账号已停用",
        )
    # 使用初始密码的员工必须先完成密码修改。
    if employee.must_change_password:
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="请先修改初始密码",
        )

    # 第二步：检查员工角色。店长和正式员工可以进入后续判断，契约工不能修改。
    if employee.role not in (
        EmployeeRole.STORE_MANAGER,
        EmployeeRole.REGULAR_EMPLOYEE,
    ):
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="只有店长或正式员工可以修改商品资料",
        )

    # 第三步：查询准备修改的商品，同时加载商品所属部门和分类。
    product = await get_product_by_id(
        product_id=product_id,
        db=db,
    )
    if product is None:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail="商品不存在",
        )

    # 第四步：检查部门权限。店长不受限制，正式员工只能修改本部门商品。
    if (
        employee.role == EmployeeRole.REGULAR_EMPLOYEE
        and employee.department_id != product.department_id
    ):
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="正式员工只能修改自己所属部门的商品",
        )

    # 第五步：把 Pydantic 请求模型转换成字典。
    # exclude_unset=True 表示只保留前端实际传入的字段，未传字段不会覆盖数据库原值。
    update_data = request.model_dump(exclude_unset=True, exclude={"reason"})
    if not update_data:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail="至少传入一个需要修改的字段",
        )

    # 第六步：检查数据库必填字段。
    # name、category_id 和 sale_price 在数据库中不允许为空。
    # 请求模型允许写 null 是为了表达可选字段，因此需要在业务层拦截显式 null。
    if "name" in update_data and update_data["name"] is None:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail="商品名称不能为空",
        )
    if "category_id" in update_data and update_data["category_id"] is None:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail="商品分类不能为空",
        )
    if "sale_price" in update_data and update_data["sale_price"] is None:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail="销售价格不能为空",
        )

    # 第七步：当前端传入 category_id 时，验证新分类是否可以使用。
    new_category_id = update_data.get("category_id")
    if isinstance(new_category_id, int):
        category = await get_category_by_id(category_id=new_category_id, db=db)
        if category is None:
            raise HTTPException(
                status_code=http_status.HTTP_404_NOT_FOUND,
                detail="商品分类不存在",
            )
        if not category.is_active:
            raise HTTPException(
                status_code=http_status.HTTP_400_BAD_REQUEST,
                detail="商品分类已停用",
            )
        if category.department_id != product.department_id:
            raise HTTPException(
                status_code=http_status.HTTP_400_BAD_REQUEST,
                detail="商品只能修改为所属部门下的分类",
            )

    # 第八步：调用 CRUD 执行 UPDATE，并重新查询更新后的商品。
    previous_data = {field: getattr(product, field) for field in update_data}
    updated_product = await update_product(
        product_id=product_id,
        update_data=update_data,
        db=db,
    )

    await create_operation_audit_log(
        employee_id=employee.id,
        module="product",
        action="update_details",
        target_type="product",
        target_id=product.id,
        before_data=previous_data,
        after_data=update_data,
        reason=request.reason,
        db=db,
    )

    # 第九步：所有校验和数据库操作都成功后，正式提交本次事务。
    await db.commit()

    # 第十步：将 Product ORM 对象转换成接口声明的 ItemResponse 响应模型。
    # from_attributes=True 允许 Pydantic 读取 Product、department 和 category 的属性。
    return ItemResponse.model_validate(updated_product)


# endregion


__all__ = [
    "get_product_detail_service",
    "get_products_list_service",
    "update_product_status_service",
    "update_product_service",
]
