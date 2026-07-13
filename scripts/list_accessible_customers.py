from __future__ import annotations

from google_ads_common import google_ads_client


def main() -> None:
    client = google_ads_client()
    customer_service = client.get_service("CustomerService")
    response = customer_service.list_accessible_customers()

    print("Customer accessibili:")
    for resource_name in response.resource_names:
        print(f"- {resource_name.replace('customers/', '')}")


if __name__ == "__main__":
    main()
