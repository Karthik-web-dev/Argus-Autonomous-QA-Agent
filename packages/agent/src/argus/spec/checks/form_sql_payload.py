from .common import define_check

CHECK = define_check(
    id="form-sql-payload",
    title="SQL-shaped input",
    category="forms",
    family="form",
    action="fill",
    value="' OR '1'='1",
    expected="SQL-shaped input is safely treated as ordinary user data.",
    flow="payload",
)

