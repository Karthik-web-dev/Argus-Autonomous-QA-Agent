from .common import define_check

CHECK = define_check(
    id="form-rtl-text",
    title="Right-to-left text",
    category="forms",
    family="form",
    action="fill",
    value="مرحبا بالعالم",
    expected="Right-to-left text remains intact and readable in the field and resulting view.",
    flow="preserve",
)
