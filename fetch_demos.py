import io
import os
import zipfile
from typing import Tuple
from boto3 import client as Client
from dotenv import load_dotenv

# Load environment file with region, key, and secret
load_dotenv(".env")


def fetch_demos(
    season: int, team: str, include_preseason: bool = False
) -> Tuple[str, int]:
    """

    :param season: Season to get demos from
    :param team: Team to fetch demos for
    :param include_preseason: Whether to download preseason matches or not
    :return: Directory all demos were downloaded in
    """

    # Create base directory
    dir = os.path.join("temp-demos", team)
    if not os.path.exists(dir):
        os.makedirs(dir)

    # Get list of demos from demos.csconfederation.com
    bucket = "cscdemos"
    client = Client(
        "s3",
        endpoint_url=f"https://{os.environ['SPACES_REGION']}.digitaloceanspaces.com",
        region_name=os.environ["SPACES_REGION"],
        aws_access_key_id=os.environ["SPACES_KEY"],
        aws_secret_access_key=os.environ["SPACES_SECRET"],
    )

    # Get all match day demos
    all_demos = client.list_objects_v2(
        Bucket=bucket,
        Prefix=f"s{season:02d}/M",
    )["Contents"]

    # Append all preseason demos
    if include_preseason:
        all_demos.append(
            client.list_objects_v2(
                Bucket=bucket,
                Prefix=f"s{season:02d}/P",
            )["Contents"]
        )

    # Filter demos to only team demos and remove any directories (S3 includes the buckets for some reason in the results)
    demo_paths = [
        x["Key"] for x in all_demos if team in x["Key"] and ".dem" in x["Key"]
    ]
    for demo_path in demo_paths:
        filename = os.path.join(dir, os.path.basename(demo_path))
        file = client.get_object(Bucket=bucket, Key=demo_path)["Body"].read()

        with (
            zipfile.ZipFile(io.BytesIO(file)) as zipped,
            open(filename, "wb") as output,
        ):
            with zipped.open(zipped.filelist[0]) as f:
                output.write(f.read())

    return (dir, len(demo_paths))
