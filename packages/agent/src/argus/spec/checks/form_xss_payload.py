from .common import define_check

CHECK = define_check(
    id="form-xss-payload",
    title="XSS-shaped input",
    category="forms",
    family="form",
    action="fill",
    value="<script>alert(1)</script>",
    expected="Untrusted markup is treated as data and never executes.",
    flow="payload",
)

