import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from lxml import etree

logger = logging.getLogger(__name__)

load_dotenv()


def migrate(xml_name: str = None, target_dir_name: str = None):
    xml_path, target_dir = parse_paths(xml_name, target_dir_name)
    tree = parse_xml_file(xml_path)


def parse_paths(xml_name: str = None, target_dir_name: str = None) -> tuple[Path, Path]:
    if xml_name is None:
        xml_name = os.environ.get("XML_PATH")
    if target_dir_name is None:
        target_dir_name = os.environ.get("TARGET_DIR")

    if not xml_name or not target_dir_name:
        raise ValueError(
            f"`xml_name` and `target_dir_name` must be provided or set in `.env`. "
            f"Found {xml_name=} and {target_dir_name=}"
        )

    xml_path = Path(xml_name)
    target_dir = Path(target_dir_name)

    if not xml_path.exists():
        raise FileNotFoundError(f"XML file not found at {xml_path}")
    if not target_dir.exists():
        raise FileNotFoundError(f"Target directory not found at {target_dir}")

    return xml_path, target_dir


def parse_xml_file(xml_path: Path) -> etree._ElementTree:
    try:
        tree = etree.parse(str(xml_path))
        return tree
    except etree.XMLSyntaxError as e:
        raise ValueError(f"Failed to parse XML file at {xml_path}: {e}")


if __name__ == "__main__":
    migrate()
