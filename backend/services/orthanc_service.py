import os
import requests

ORTHANC_URL = os.getenv("ORTHANC_URL", "http://orthanc-pacs:8042")
ORTHANC_USER = os.getenv("ORTHANC_USER")
ORTHANC_PASSWORD = os.getenv("ORTHANC_PASSWORD")

ORTHANC_PUBLIC_URL = os.getenv(
    "ORTHANC_PUBLIC_URL",
    "http://localhost:8042"
)


def auth():
    if ORTHANC_USER and ORTHANC_PASSWORD:
        return (ORTHANC_USER, ORTHANC_PASSWORD)
    return None


def subir_dicom_a_orthanc(ruta_archivo: str):

    with open(ruta_archivo, "rb") as f:
        r = requests.post(
            f"{ORTHANC_URL}/instances",
            data=f,
            auth=auth(),
            timeout=60,
        )

    r.raise_for_status()

    data = r.json()

    instance_id = data.get("ID")
    parent_study = data.get("ParentStudy")

    study_instance_uid = None

    if parent_study:

        r2 = requests.get(
            f"{ORTHANC_URL}/studies/{parent_study}",
            auth=auth(),
            timeout=30,
        )

        r2.raise_for_status()

        study_data = r2.json()

        study_instance_uid = (
            study_data
            .get("MainDicomTags", {})
            .get("StudyInstanceUID")
        )

    return {
        "orthanc_instance_id": instance_id,
        "orthanc_study_id": parent_study,
        "study_instance_uid": study_instance_uid,
    }


def url_study_explorer(study_id: str):
    return f"{ORTHANC_PUBLIC_URL}/app/explorer.html#study?uuid={study_id}"


def url_instance_preview(study_instance_uid: str):
    return f"{ORTHANC_PUBLIC_URL}/ui/app/#/filtered-studies?StudyInstanceUID={study_instance_uid}"
