from .common import define_check

CHECK = define_check(
    id="form-unicode",
    title="Unicode input",
    category="forms",
    family="form",
    action="fill",
    value="Zoë 李 😊",
    expected="Unicode input is accepted or rejected according to the field contract without encoding loss.",
    flow="preserve",
)

