"""
Serviço de processamento de arquivos IFC usando IfcOpenShell.
Extrai elementos do modelo BIM para análise de progresso de obra.
"""

import tempfile
from datetime import datetime
from pathlib import Path

import ifcopenshell
import structlog

logger = structlog.get_logger(__name__)


class IFCProcessorService:
    """Serviço para processar arquivos IFC e extrair informações do modelo BIM."""

    def __init__(self, embedding_service=None):
        self.supported_types = [
            "IfcWall",
            "IfcWallStandardCase",
            "IfcSlab",
            "IfcColumn",
            "IfcBeam",
            "IfcDoor",
            "IfcWindow",
            "IfcStair",
            "IfcRoof",
            "IfcFooting",
            "IfcPile",
            "IfcRailing",
            "IfcCurtainWall",
        ]
        self.embedding_service = embedding_service

    async def process_ifc_file(self, file_content: bytes) -> dict:
        """
        Processa arquivo IFC e extrai estrutura do modelo.

        Args:
            file_content: Conteúdo do arquivo IFC em bytes

        Returns:
            Dicion with project info, elements, and metadata
        """
        try:
            logger.info("iniciando_processamento_ifc")

            # Salva temporariamente
            with tempfile.NamedTemporaryFile(delete=False, suffix=".ifc") as temp_file:
                temp_file.write(file_content)
                temp_path = temp_file.name

            try:
                ifc_file = ifcopenshell.open(temp_path)

                project_info = await self._extract_project_info(ifc_file)
                elements = await self._extract_elements(ifc_file)

                result = {
                    "project_info": project_info,
                    "total_elements": len(elements),
                    "elements": elements,
                    "processed_at": datetime.utcnow().isoformat(),
                }

                logger.info(
                    "ifc_processado",
                    total_elements=len(elements),
                    project_name=project_info.get("project_name"),
                )

                return result

            finally:
                Path(temp_path).unlink(missing_ok=True)

        except Exception as e:
            logger.error("erro_processar_ifc", error=str(e), exc_info=True)
            raise

    async def _extract_project_info(self, ifc_file) -> dict:
        """Extrai informações básicas do projeto."""
        try:
            project = ifc_file.by_type("IfcProject")[0]
            site = ifc_file.by_type("IfcSite")
            building = ifc_file.by_type("IfcBuilding")

            return {
                "project_name": project.Name if hasattr(project, "Name") else "Sem nome",
                "description": project.Description if hasattr(project, "Description") else None,
                "site_name": site[0].Name if site and hasattr(site[0], "Name") else None,
                "building_name": (
                    building[0].Name if building and hasattr(building[0], "Name") else None
                ),
            }

        except Exception as e:
            logger.warning("erro_extrair_info_projeto", error=str(e))
            return {}

    async def _extract_elements(self, ifc_file) -> list[dict]:
        """Extrai elementos estruturais do modelo IFC."""
        elements = []

        for ifc_type in self.supported_types:
            try:
                items = ifc_file.by_type(ifc_type)

                for item in items:
                    element = await self._parse_element(item, ifc_type)
                    if element:
                        elements.append(element)

            except Exception as e:
                logger.warning("erro_processar_tipo", ifc_type=ifc_type, error=str(e))
                continue

        return elements

    async def _parse_element(self, ifc_element, element_type: str) -> dict | None:
        """Parse um elemento IFC individual."""
        try:
            element_id = ifc_element.GlobalId if hasattr(ifc_element, "GlobalId") else None
            name = ifc_element.Name if hasattr(ifc_element, "Name") else None

            properties = self._extract_properties(ifc_element)
            geometry = self._extract_geometry(ifc_element)

            return {
                "element_id": element_id,
                "element_type": element_type.replace("Ifc", ""),
                "name": name,
                "properties": properties,
                "geometry": geometry,
                "scheduled_date": None,
            }

        except Exception as e:
            logger.warning("erro_parsear_elemento", error=str(e))
            return None

    def _extract_properties(self, ifc_element) -> dict:
        """Extrai propriedades de um elemento IFC."""
        properties = {}

        try:
            if hasattr(ifc_element, "IsDefinedBy"):
                for definition in ifc_element.IsDefinedBy:
                    if definition.is_a("IfcRelDefinesByProperties"):
                        property_set = definition.RelatingPropertyDefinition

                        if property_set.is_a("IfcPropertySet"):
                            for prop in property_set.HasProperties:
                                if prop.is_a("IfcPropertySingleValue"):
                                    prop_name = prop.Name
                                    prop_value = (
                                        prop.NominalValue.wrappedValue if prop.NominalValue else None
                                    )
                                    properties[prop_name] = prop_value

            if hasattr(ifc_element, "Description") and ifc_element.Description:
                properties["Description"] = ifc_element.Description

            if hasattr(ifc_element, "ObjectType") and ifc_element.ObjectType:
                properties["ObjectType"] = ifc_element.ObjectType

        except Exception as e:
            logger.warning("erro_extrair_propriedades", error=str(e))

        return properties

    def _extract_geometry(self, ifc_element) -> dict | None:
        """Extrai informações geométricas básicas."""
        try:
            has_geometry = hasattr(ifc_element, "Representation") and ifc_element.Representation
            return {"has_representation": has_geometry}

        except Exception as e:
            logger.warning("erro_extrair_geometria", error=str(e))
            return None

    async def generate_embeddings_context(self, elements: list[dict]) -> list[str]:
        """
        Gera contextos textuais dos elementos para embeddings.

        Args:
            elements: Lista de elementos processados

        Returns:
            Lista de strings descritivas
        """
        contexts = []

        for element in elements:
            context = f"{element['element_type']}"

            if element.get("name"):
                context += f" - {element['name']}"

            if element.get("properties"):
                props = element["properties"]
                if "Description" in props:
                    context += f" - {props['Description']}"
                if "ObjectType" in props:
                    context += f" - {props['ObjectType']}"

            contexts.append(context)

        return contexts

    async def index_elements_to_opensearch(self, project_id: str, elements: list[dict]) -> int:
        """
        Indexa elementos BIM no OpenSearch com embeddings.

        Args:
            project_id: ID do projeto
            elements: Lista de elementos processados

        Returns:
            Número de elementos indexados
        """
        if not self.embedding_service:
            logger.warning("embedding_service_nao_configurado")
            return 0

        try:
            from app.models.opensearch import BIMElementEmbedding

            indexed_count = 0

            for element in elements:
                # Gera contexto textual
                context = f"{element['element_type']}"
                if element.get("name"):
                    context += f" {element['name']}"

                # Propriedades como texto
                props_text = ""
                if element.get("properties"):
                    props_text = " ".join([f"{k}: {v}" for k, v in element["properties"].items()])

                # Gera embedding
                embedding_vector = await self.embedding_service.generate_embedding(context)

                # Cria documento OpenSearch
                doc = BIMElementEmbedding(
                    element_id=element["element_id"],
                    project_id=project_id,
                    element_type=element["element_type"],
                    description=context,
                    element_name=element.get("name", ""),
                    properties_text=props_text,
                    embedding=embedding_vector,
                )
                doc.save()
                indexed_count += 1

            logger.info("elementos_indexados", count=indexed_count, project_id=project_id)
            return indexed_count

        except Exception as e:
            logger.error("erro_indexar_elementos", error=str(e), exc_info=True)
            return 0
