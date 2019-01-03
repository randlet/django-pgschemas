from django.conf import settings
from django.db import connection
from django.http import Http404

from .postgresql_backend.base import VolatileTenant
from .utils import remove_www, get_domain_model


class TenantMiddleware:
    """
    This middleware should be placed at the very top of the middleware stack.
    Selects the proper static/database schema using the request host. Can fail in
    various ways which is better than corrupting or revealing data.
    """

    TENANT_NOT_FOUND_EXCEPTION = Http404

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        hostname = remove_www(request.get_host().split(":")[0])
        connection.set_schema_to_public()

        # Checking for static tenants
        for schema, data in settings.TENANTS.items():
            if schema in ["public", "default"]:
                continue
            if hostname in data["DOMAINS"]:
                tenant = VolatileTenant(schema_name=schema)
                tenant.domain_url = hostname
                request.tenant = tenant
                if "URLCONF" in data:
                    request.urlconf = data["URLCONF"]
                connection.set_schema(schema)
                return self.get_response(request)
        # Checking for dynamic tenants
        else:
            DomainModel = get_domain_model()
            try:
                domain = DomainModel.objects.select_related("tenant").get(domain=hostname)
                tenant = domain.tenant
            except DomainModel.DoesNotExist:
                raise self.TENANT_NOT_FOUND_EXCEPTION("No tenant for hostname '%s'" % hostname)
            tenant.domain_url = hostname
            request.tenant = tenant
            request.urlconf = settings.ROOT_URLCONF
            connection.set_schema(request.tenant.schema_name)
            return self.get_response(request)