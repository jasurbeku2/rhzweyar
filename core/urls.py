from django.urls import path
from . import views as v
urlpatterns = [
    path("", v.home, name="home"),
    path("login/", v.login_view, name="login"),
    path("verify/", v.verify_view, name="verify"),
    path("logout/", v.logout_view, name="logout"),
    path("premium/", v.premium, name="premium"),
    path("services/", v.services, name="services"),
    path("pay/<str:kind>/<int:pk>/", v.pay, name="pay"),
    path("promo/", v.promo, name="promo"),
    path("profile/", v.profile, name="profile"),
]
