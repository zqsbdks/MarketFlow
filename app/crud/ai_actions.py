"""ai_actions：数据库读写函数。"""

from app.models.employee import Employee


async def get_action_employee(db, employee_id):
    """执行confirm_ai_action_service所需的数据库查询；权限由调用它的服务检查。"""
    return await db.get(Employee, employee_id)
