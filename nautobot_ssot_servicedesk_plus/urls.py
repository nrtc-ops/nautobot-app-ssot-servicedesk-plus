"""Django urlpatterns declaration for nautobot_ssot_servicedesk_plus app."""

from django.templatetags.static import static
from django.urls import path
from django.views.generic import RedirectView
from nautobot.apps.urls import NautobotUIViewSetRouter


# Uncomment the following line if you have views to import
# from nautobot_ssot_servicedesk_plus import views


app_name = "nautobot_ssot_servicedesk_plus"
router = NautobotUIViewSetRouter()

# Here is an example of how to register a viewset, you will want to replace views.NautobotSsotServicedeskPlusUIViewSet with your viewset
# router.register("nautobot_ssot_servicedesk_plus", views.NautobotSsotServicedeskPlusUIViewSet)


urlpatterns = [
    path("docs/", RedirectView.as_view(url=static("nautobot_ssot_servicedesk_plus/docs/index.html")), name="docs"),
]

urlpatterns += router.urls
