from django.db import migrations


def delete_builtin_categories(apps, schema_editor):
    """Pharmacies now create their own categories. A built-in one that a medicine still uses is kept (a medicine needs a category)
    and simply becomes an ordinary category the pharmacy can rename or, once unused, delete."""
    Category = apps.get_model("medicines", "Category")
    Medicine = apps.get_model("medicines", "Medicine")
    db = schema_editor.connection.alias
    used = Medicine._base_manager.using(db).values("category_id")
    Category._base_manager.using(db).filter(is_system=True).exclude(pk__in=used).delete()


class Migration(migrations.Migration):
    dependencies = [("medicines", "0001_initial")]
    operations = [migrations.RunPython(delete_builtin_categories, migrations.RunPython.noop)]
