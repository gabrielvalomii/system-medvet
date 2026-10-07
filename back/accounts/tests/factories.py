import factory

from accounts.models import User

DEFAULT_PASSWORD = "S3nha-Forte!2026"


class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = User
        skip_postgeneration_save = True

    email = factory.Sequence(lambda n: f"user{n}@example.com")
    first_name = "Maria"
    last_name = "Silva"

    @factory.post_generation
    def password(obj, create, extracted, **kwargs):  # noqa: N805
        obj.set_password(extracted or DEFAULT_PASSWORD)
        if create:
            obj.save()
