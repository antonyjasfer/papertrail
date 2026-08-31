import sys
import os

# Import DNS fix
sys.path.insert(0, r"C:\Users\anton\OneDrive\Desktop\papertrail\papertrail\scratch\dns_fix")
import sitecustomize

# Add Azure CLI packages to sys.path
az_site_packages = r"C:\Program Files\Microsoft SDKs\Azure\CLI2\Lib\site-packages"
if os.path.exists(az_site_packages):
    sys.path.insert(0, az_site_packages)

from azure.cli.core import get_default_cli

def main():
    args = sys.argv[1:]
    cli = get_default_cli()
    status = cli.invoke(args)
    sys.exit(status)

if __name__ == "__main__":
    main()
