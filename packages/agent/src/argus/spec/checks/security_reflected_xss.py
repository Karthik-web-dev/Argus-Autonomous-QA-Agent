from .common import define_check

CHECK = define_check(
    id="security-reflected-xss",
    title="Reflected XSS input",
    category="security",
    family="form",
    action="fill",
    value="<img src=x onerror=alert(1)>",
    expected="Reflected input is escaped and cannot execute as markup.",
    flow="payload",
)

