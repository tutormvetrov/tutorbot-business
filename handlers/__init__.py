from loader import dp
from handlers.users import start, menu, callbacks, admin, product
from handlers.users.admin_sections import broadcast, calendar_aliases, health, homework, notes, payments, students

# Порядок важен: admin регистрируется первым, чтобы его специфичные
# фильтры (StateFilter + FSM) имели приоритет над общими.
dp.include_router(admin.router)
dp.include_router(students.router)
dp.include_router(payments.router)
dp.include_router(homework.router)
dp.include_router(broadcast.router)
dp.include_router(calendar_aliases.router)
dp.include_router(notes.router)
dp.include_router(health.router)
dp.include_router(start.router)
dp.include_router(menu.router)
dp.include_router(product.router)
dp.include_router(callbacks.router)
