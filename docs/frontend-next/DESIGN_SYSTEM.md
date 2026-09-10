# Design system

Направление: ясный технический workspace, тихая типографика, точный ритм таблиц, одна акцентная синяя шкала. Основной visual anchor — информационная иерархия рабочего пространства, не декоративные изображения.

Один набор primitives и semantic tokens, ровно light/dark. Источник tokens: frontend/src/styles/tokens.css.
- Поверхности: background, surface, surface-raised, surface-hover, surface-active.
- Текст: primary, secondary, muted, disabled. Границы: border, border-strong.
- Значение состояния: success, warning, danger, info; обязательно текст вместе с цветом.
- Spacing: 4 / 8 / 12 / 16 / 20 / 24 / 32 / 40 / 48.
- Controls 36px, компактные 30px; radius 4/7/10px.
- Sans: системный Segoe UI Variable / Segoe UI / Arial. Технические значения: Cascadia / SFMono / Consolas.
- Desktop navigation 222px, toolbar 60px. Основная ширина до 1600px.
- Motion 120/180ms, reduced-motion учитывается.
- Фокус видим. Radix отвечает за trapping/escape/focus-return в modal/drawer.
- Table, Panel, PageHeader, Field, Feedback, EmptyState, StatusBadge и ConfirmDialog — общие.
- Визуальный текст не содержит сведений о реализации или вымышленных production показателей.

Storybook каталог проверяет базовые состояния и обе темы. Reusable CSS helpers не должны превращаться в вторую дизайн-систему.

