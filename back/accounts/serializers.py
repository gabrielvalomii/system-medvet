from rest_framework import serializers

from .models import User


class LoginSerializer(serializers.Serializer):
    """Valida apenas o formato do payload de login; a autenticação fica na view."""

    email = serializers.EmailField(max_length=254)
    password = serializers.CharField(
        max_length=128, trim_whitespace=False, write_only=True
    )

    def validate_email(self, value: str) -> str:
        return User.objects.normalize_email(value)


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ("id", "email", "first_name", "last_name")
        read_only_fields = fields
