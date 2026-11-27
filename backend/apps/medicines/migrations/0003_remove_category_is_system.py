from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("medicines", "0002_delete_builtin_categories")]
    operations = [migrations.RemoveField(model_name="category", name="is_system")]
