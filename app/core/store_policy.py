"""请求门店上下文与统一数据隔离；跨店可读，本店按角色可写。"""
from fastapi import HTTPException
from sqlalchemy import event, inspect, select
from sqlalchemy.orm import Session, with_loader_criteria

from app.models.store_scoped import StoreScopedMixin
from app.models.employee import Employee
from app.models.enums import EmployeeRole
from app.models.store import Store, StoreDepartment
from app.models.department import Department
from app.models.category import Category
from app.models.operation_audit_log import OperationAuditLog

# region 请求上下文
async def configure_store_context(request, employee, db):
    """门店由最新员工归属和查询选择决定，不信任前端写入的归属字段。"""
    headquarters = employee.role == EmployeeRole.HEADQUARTERS
    raw = request.headers.get("X-Store-ID") or request.query_params.get("store_id")
    selected = employee.store_id
    if raw:
        if raw == "all":
            if not headquarters or not request.url.path.endswith(("/overview", "/departments", "/analytics")):
                raise HTTPException(403, "只有总部经营报表支持全公司汇总")
            selected = None
        else:
            try:
                selected = int(raw)
            except ValueError as exc:
                raise HTTPException(422, "门店ID无效") from exc
            if selected <= 0:
                raise HTTPException(422, "门店ID无效")
    # 门店管理和私人AI设置不依赖查询门店；总部默认选择首家店供业务查询。
    if selected is None and headquarters and raw != "all":
        selected = await db.scalar(select(Store.id).where(Store.is_active.is_(True)).order_by(Store.id).limit(1))
    if selected is not None:
        store = await db.get(Store, selected)
        if store is None or not store.is_active:
            raise HTTPException(403, "门店不存在或已停用")
    path = request.url.path
    company_management = "/stores" in path
    notices = "/contact-notices" in path
    ai = "/ai-chat" in path
    account = "/auth/" in path
    # 门店员工的联络事项归属自己的店，和查询下拉框无关。
    if notices and not headquarters:
        selected = employee.store_id
    is_query = request.method in ("GET", "HEAD", "OPTIONS") or path.endswith("/preview")
    if not is_query and not (company_management or notices or ai or account):
        if headquarters:
            raise HTTPException(403, "总部不执行门店日常业务")
        if selected != employee.store_id:
            raise HTTPException(403, "跨店查看为只读，不能修改其他门店")
    if not headquarters and employee.store_id is None:
        raise HTTPException(403, "员工尚未分配门店")
    db.info.update(actor_id=employee.id, actor_role=employee.role, own_store_id=employee.store_id,
        read_store_id=selected, write_store_id=employee.store_id,
        company_management=company_management,
        company_catalog_read=company_management or (notices and headquarters),
        private_employee_path="/employees" in path or ai,
        store_context=True)
    request.state.store_id = selected
    request.state.employee_id = employee.id
    request.state.own_store_id = employee.store_id
    if "/employees" in path and not headquarters and selected != employee.store_id:
        raise HTTPException(403, "不能跨店查看员工私人资料")
# endregion

# region 查询与写入隔离
@event.listens_for(Session, "do_orm_execute")
def restrict_store_queries(state):
    """统一约束 ORM 查询与批量更新，关系预加载也携带门店条件。"""
    info = state.session.info
    if not info.get("store_context"):
        return
    store_id = info.get("read_store_id")
    if state.is_select:
        if info["actor_role"] != EmployeeRole.HEADQUARTERS:
            state.statement = state.statement.options(with_loader_criteria(
                OperationAuditLog, OperationAuditLog.store_id == info["own_store_id"], include_aliases=True))
        if store_id is not None:
            state.statement = state.statement.options(with_loader_criteria(
                StoreScopedMixin, lambda cls: cls.store_id == store_id, include_aliases=True))
            enabled = select(StoreDepartment.department_id).where(
                StoreDepartment.store_id == store_id, StoreDepartment.is_active.is_(True))
            if not info.get("company_catalog_read"):
                state.statement = state.statement.options(
                    with_loader_criteria(Department, Department.id.in_(enabled), include_aliases=True),
                    with_loader_criteria(Category, Category.department_id.in_(enabled), include_aliases=True))
        if info.get("private_employee_path") and info["actor_role"] != EmployeeRole.HEADQUARTERS and not state.is_relationship_load:
            own = info["own_store_id"]
            state.statement = state.statement.options(with_loader_criteria(Employee, Employee.store_id == own, include_aliases=True))
    elif state.is_update or state.is_delete:
        mapper = state.bind_mapper
        if mapper is None:
            raise HTTPException(403, "业务写入必须使用已验证的ORM模型")
        model = mapper.class_
        if issubclass(model, StoreScopedMixin):
            assert_store_write(info, store_id)
            state.statement = state.statement.where(model.store_id == info["own_store_id"])
        elif model is Employee and not info.get("company_management"):
            if info["actor_role"] == EmployeeRole.HEADQUARTERS:
                raise HTTPException(403, "总部员工调整请使用专用管理接口")
            state.statement = state.statement.where(Employee.store_id == info["own_store_id"])

def assert_store_write(info, target_store):
    if info["actor_role"] == EmployeeRole.HEADQUARTERS:
        raise HTTPException(403, "总部不能修改门店业务数据")
    if target_store != info.get("own_store_id"):
        raise HTTPException(403, "只能修改所属门店数据")

@event.listens_for(Session, "before_flush")
def validate_store_objects(session, flush_context, instances):
    """新增数据自动归店，阻止跨店对象写入，检查部门启用配置。"""
    info = session.info
    for obj in list(session.new) + list(session.dirty) + list(session.deleted):
        if isinstance(obj, StoreScopedMixin):
            if obj in session.new and info.get("write_store_id") is not None:
                if obj.store_id is not None and obj.store_id != info["write_store_id"]:
                    raise HTTPException(403, "数据归属门店不一致")
                obj.store_id = info["write_store_id"]
            if info.get("store_context"):
                assert_store_write(info, obj.store_id)
                department_id = getattr(obj, "department_id", None)
                if department_id is not None and obj not in session.deleted:
                    enabled = session.scalar(select(StoreDepartment.is_active).where(
                        StoreDepartment.store_id == obj.store_id, StoreDepartment.department_id == department_id))
                    if not enabled:
                        raise HTTPException(400, "本店未启用此部门")
        if isinstance(obj, Employee) and info.get("store_context") and not info.get("company_management"):
            changes = inspect(obj)
            if obj in session.new:
                if obj.role in (EmployeeRole.HEADQUARTERS, EmployeeRole.STORE_MANAGER):
                    raise HTTPException(403, "只有总部可以任命店长或创建总部账号")
                obj.store_id = info["own_store_id"]
            else:
                if changes.attrs.store_id.history.has_changes() or changes.attrs.role.history.has_changes():
                    raise HTTPException(403, "只有总部可以调整门店归属或任命角色")
                if obj.id != info["actor_id"] and obj.store_id != info["own_store_id"]:
                    raise HTTPException(403, "不能修改其他门店员工")
            if obj.department_id is not None:
                enabled = session.scalar(select(StoreDepartment.is_active).where(
                    StoreDepartment.store_id == obj.store_id, StoreDepartment.department_id == obj.department_id))
                if not enabled:
                    raise HTTPException(400, "员工部门尚未在所属门店启用")
# endregion
