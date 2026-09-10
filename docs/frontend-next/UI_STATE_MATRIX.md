# UI state matrix

| State | Представление | Действие |
|---|---|---|
| loading | skeleton / loader с ролью status | мутации блокируются до готовности |
| empty | конкретная причина + создание/подключение | без fake data |
| error | понятный текст, retry | данные ошибки не пропадают |
| partial | успешные секции сохраняются | отдельно показываем отказавший источник |
| stale | время измерения/refresh | не считать метрику live |
| disabled | причина рядом с control | не предлагает недоступное действие |
| permission denied | роль/объект недоступны | запросить доступ у администратора |
| offline | глобальный notice и безопасный retry | не повторять команды автоматически |
| connecting/reconnecting | connection badge | ручное переподключение после лимита |
| success | inline confirmation + invalidation | форма закрывается только после успеха |

Form fields имеют labels, required/тип/диапазон, field + server errors. Delete — confirmation, опасный target — typed identity. Keyboard focus возвращается из drawers/dialogs. Темы переключаются единым набором tokens.

