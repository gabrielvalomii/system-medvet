from django.contrib import admin

from .models import Expense, Income


class EntryAdmin(admin.ModelAdmin):
    list_display = ("date", "user", "category", "amount", "description")
    list_filter = ("category", "date")
    search_fields = ("description", "user__email")
    date_hierarchy = "date"
    ordering = ("-date", "-id")
    list_select_related = ("user",)
    autocomplete_fields = ("user",)
    readonly_fields = ("created_at", "updated_at")


@admin.register(Expense)
class ExpenseAdmin(EntryAdmin):
    pass


@admin.register(Income)
class IncomeAdmin(EntryAdmin):
    pass
