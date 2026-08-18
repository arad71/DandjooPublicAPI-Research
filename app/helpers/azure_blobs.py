from azure.storage.blob import BlobClient, StorageStreamDownloader

from app.settings import Settings


def check_blob_store_available(settings: Settings) -> bool:
    return bool(settings.azure_account_name and settings.azure_account_key)


def get_blob_downloader(
    *,
    settings: Settings,
    blob_url: str,
    use_credentials: bool,
) -> StorageStreamDownloader:
    """
    Get a "StorageStreamDownloader" object to download the blob.

    :param settings: Settings object
    :param blob_url: URL of the blob
    :param use_credentials: True if credentials should be used, False otherwise.
        Public blobs should not use credentials, otherwise an error will happen.
    """
    blob_client = BlobClient.from_blob_url(
        blob_url,
        credential=(
            {
                "account_name": settings.azure_account_name,
                "account_key": settings.azure_account_key,
            }
            if use_credentials
            else None
        ),
    )

    # check blob exists, and check that our credentials are valid for the blob.
    if not blob_client.exists():
        raise Exception(f"Blob with url {blob_url} does not exist")

    return blob_client.download_blob()


