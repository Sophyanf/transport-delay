import importlib.util
import inspect
from pathlib import Path
from types import ModuleType
from typing import Any

from transport_model_core.manifest import (
    ModelManifest,
    load_model_manifest,
)
from transport_model_core.protocol import DelayModel


class ModelLoader:
    # Создаёт загрузчик моделей из указанного каталога.
    def __init__(self, model_root: Path) -> None:
        self._model_root = model_root.resolve()

    # Загружает готовую модель вместе с артефактом.
    def load(
        self,
        plugin: str,
        version: str,
    ) -> DelayModel:
        model = self.create(plugin, version)
        model.load()
        return model

    # Создаёт модель без загрузки обученного артефакта.
    def create(
        self,
        plugin: str,
        version: str,
    ) -> DelayModel:
        plugin_directory = self._create_plugin_directory(plugin)
        manifest = load_model_manifest(plugin_directory / "model.yaml")
        self._create_validate_version(manifest, version)
        model_class = self._create_model_class(plugin_directory, manifest)
        model = model_class(
            manifest=manifest,
            plugin_directory=plugin_directory,
        )
        self._create_validate_contract(model)
        return model

    # Возвращает манифест выбранного плагина.
    def manifest(self, plugin: str) -> ModelManifest:
        plugin_directory = self._create_plugin_directory(plugin)
        return load_model_manifest(plugin_directory / "model.yaml")

    # Возвращает безопасный путь к папке плагина.
    def _create_plugin_directory(self, plugin: str) -> Path:
        self._create_validate_plugin_name(plugin)
        plugin_directory = (self._model_root / plugin).resolve()
        if self._model_root not in plugin_directory.parents:
            raise ValueError("Plugin path escapes model root")
        if not plugin_directory.is_dir():
            raise FileNotFoundError(plugin_directory)
        return plugin_directory

    # Проверяет допустимость имени плагина.
    def _create_validate_plugin_name(self, plugin: str) -> None:
        allowed = plugin.replace("_", "").replace("-", "")
        if not plugin or not allowed.isalnum():
            raise ValueError(f"Invalid plugin name: {plugin!r}")

    # Проверяет соответствие версии запросу.
    def _create_validate_version(
        self,
        manifest: ModelManifest,
        version: str,
    ) -> None:
        if manifest.version != version:
            raise ValueError(f"Version mismatch: requested={version}, manifest={manifest.version}")

    # Загружает класс модели из entrypoint.
    def _create_model_class(
        self,
        plugin_directory: Path,
        manifest: ModelManifest,
    ) -> type[Any]:
        source_name, class_name = manifest.entrypoint.split("::", maxsplit=1)
        source_path = (plugin_directory / source_name).resolve()
        self._create_validate_source(plugin_directory, source_path)
        module = self._create_load_module(source_path, manifest)
        model_class = getattr(module, class_name, None)
        if not inspect.isclass(model_class):
            raise TypeError(f"Entrypoint is not a class: {manifest.entrypoint}")
        return model_class

    # Проверяет путь исходного файла плагина.
    def _create_validate_source(
        self,
        plugin_directory: Path,
        source_path: Path,
    ) -> None:
        if plugin_directory not in source_path.parents:
            raise ValueError("Entrypoint escapes plugin directory")
        if not source_path.is_file():
            raise FileNotFoundError(source_path)

    # Импортирует Python-модуль по абсолютному пути.
    def _create_load_module(
        self,
        source_path: Path,
        manifest: ModelManifest,
    ) -> ModuleType:
        module_name = self._create_module_name(manifest)
        specification = importlib.util.spec_from_file_location(
            module_name,
            source_path,
        )
        if specification is None or specification.loader is None:
            raise ImportError(f"Cannot load module: {source_path}")
        module = importlib.util.module_from_spec(specification)
        specification.loader.exec_module(module)
        return module

    # Создаёт уникальное имя динамического модуля.
    def _create_module_name(self, manifest: ModelManifest) -> str:
        name = f"transport_plugin_{manifest.name}_{manifest.version}"
        return name.replace(".", "_").replace("-", "_")

    # Проверяет реализацию контракта DelayModel.
    def _create_validate_contract(self, model: object) -> None:
        if not isinstance(model, DelayModel):
            raise TypeError("Plugin does not implement DelayModel")
