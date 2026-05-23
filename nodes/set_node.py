
from typing import Dict, Any, List, Optional
from abc import ABC, abstractmethod
import re
import logging
from engine.registry import register_node
from engine.base_node import BaseNode
from engine.logging_config import setup_logging


logger = setup_logging(__name__, level=logging.DEBUG)



# ===== Transformation Strategy Pattern =====

class TransformStrategy(ABC):
    @abstractmethod
    def transform(self, value: Any, *args) -> Any:
        pass
    
    @abstractmethod
    def name(self) -> str:
        pass


class LowerTransform(TransformStrategy):
    def name(self) -> str:
        return "lower"
    
    def transform(self, value: Any, *args) -> Any:
        return str(value).lower()


class UpperTransform(TransformStrategy):
    def name(self) -> str:
        return "upper"
    
    def transform(self, value: Any, *args) -> Any:
        return str(value).upper()


class StripTransform(TransformStrategy):
    def name(self) -> str:
        return "strip"
    
    def transform(self, value: Any, *args) -> Any:
        return str(value).strip()


class SplitTransform(TransformStrategy):
    def name(self) -> str:
        return "split"
    
    def transform(self, value: Any, *args) -> Any:
        delimiter = args[0] if args else " "
        result = str(value).split(delimiter)
        if len(args) > 1:
            index = int(args[1])
            return result[index] if 0 <= index < len(result) else None
        return result


class JoinTransform(TransformStrategy):
    def name(self) -> str:
        return "join"
    
    def transform(self, value: Any, *args) -> Any:
        separator = args[0] if args else ""
        if isinstance(value, list):
            return separator.join(str(v) for v in value)
        return value


class LengthTransform(TransformStrategy):
    def name(self) -> str:
        return "len"
    
    def transform(self, value: Any, *args) -> Any:
        return len(value) if value else 0


class ReplaceTransform(TransformStrategy):
    def name(self) -> str:
        return "replace"
    
    def transform(self, value: Any, *args) -> Any:
        if len(args) >= 2:
            return str(value).replace(str(args[0]), str(args[1]))
        return value


class SubstringTransform(TransformStrategy):
    def name(self) -> str:
        return "substring"
    
    def transform(self, value: Any, *args) -> Any:
        if not args:
            return value
        start = int(args[0])
        end = int(args[1]) if len(args) > 1 else None
        return str(value)[start:end]


# ===== Transformation Registry =====

class TransformRegistry:
    def __init__(self):
        self._transforms: Dict[str, TransformStrategy] = {}
        self._register_default_transforms()
    
    def register(self, strategy: TransformStrategy):
        self._transforms[strategy.name()] = strategy
    
    def get(self, name: str) -> Optional[TransformStrategy]:
        return self._transforms.get(name)
    
    def _register_default_transforms(self):
        for transform in [
            LowerTransform(), UpperTransform(), StripTransform(),
            SplitTransform(), JoinTransform(), LengthTransform(),
            ReplaceTransform(), SubstringTransform()
        ]:
            self.register(transform)


transform_registry = TransformRegistry()


# ===== SetNode Implementation =====
@register_node("SetNode")
class SetNode(BaseNode):
    
    def __init__(self, node_id, node_data, registry: TransformRegistry = None):
        super().__init__(node_id, node_data)  # Now calls BaseNode.__init__
        self.config = node_data
        self.registry = registry or transform_registry
    

    # def execute(self, trigger_data: Dict[str, Any]) -> Dict[str, Any]:
    #     output = {}
    #     mappings = self.config.get("formData", {}).get("mappings", [])
        
    #     for mapping in mappings:
    #         try:
    #             field = mapping["field"]
    #             source = mapping["source"]
    #             transform = mapping.get("transform")
                
    #             value = self._extract_value(source, trigger_data)
                
    #             if transform and value is not None:
    #                 value = self._apply_transforms(value, transform)
                
    #             output[field] = value
    #             logger.debug(f"Mapped {field} = {value}")
            
    #         except Exception as e:
    #             logger.error(f"Error mapping {mapping.get('field')}: {e}", exc_info=True)
    #             output[mapping.get("field")] = None
        
    #     return output
    def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Execute the SetNode mapping"""
        if self.DEBUG_EXTRACTION:
            logger.info("\n" + "=" * 80)
            logger.info("SET NODE EXECUTION STARTED")
            logger.info("=" * 80)
            logger.info(f"Context keys: {list(context.keys())}")
            logger.info(f"Number of mappings: {len(self.node_data.get('mappings', []))}")
        
        # ALWAYS log this regardless of debug mode
        logger.info(f"SetNode.execute() called with context keys: {list(context.keys())}")
        
        output = {}
        mappings = (
            self.node_data.get('formData', {}).get('mappings', [])
        )

        
        # ALWAYS log this
        logger.info(f"Processing {len(mappings)} mappings")
        
        for idx, mapping in enumerate(mappings):
            field = mapping.get('field')
            source = mapping.get('source')
            transform = mapping.get('transform')
            
            # ALWAYS log each mapping attempt
            logger.info(f"\n>>> Attempting mapping {idx + 1}/{len(mappings)}: field='{field}', source='{source}'")
            
            if self.DEBUG_EXTRACTION:
                logger.info(f"{'*' * 80}")
                logger.info(f"Processing Mapping {idx + 1}/{len(mappings)}")
                logger.info(f"Field: '{field}'")
                logger.info(f"Source: '{source}'")
                logger.info(f"Transform: '{transform}'")
                logger.info(f"{'*' * 80}")
            
            if not field or not source:
                logger.warning(f"Skipping invalid mapping: field={field}, source={source}")
                continue
            
            # Extract value
            logger.info(f"Calling _extract_value('{source}', context)")
            value = self._extract_value(source, context)
            logger.info(f"_extract_value returned: {type(value)} = {str(value)[:100] if value is not None else 'None'}")
            
            if value is None:
                logger.warning(f"⚠ Extraction returned None for field '{field}', source '{source}'")
                logger.warning(f"   This mapping will be SKIPPED")
                continue
            
            # Apply transform if specified
            if transform:
                logger.info(f"Applying transform: {transform}")
                value = self._apply_transforms(value, transform)
                logger.info(f"Value after transform: {str(value)[:100]}")
            
            output[field] = value
            logger.info(f"✓✓✓ Successfully set output['{field}'] = {str(value)[:100]}...")
            
            if self.DEBUG_EXTRACTION:
                logger.info(f"✓ Mapping successful: '{field}' = {str(value)[:100]}...")
        
        logger.info(f"\n>>> SetNode.execute() completed. Output has {len(output)} fields: {list(output.keys())}")
        
        if self.DEBUG_EXTRACTION:
            logger.info("\n" + "=" * 80)
            logger.info("SET NODE EXECUTION COMPLETED")
            logger.info(f"Output fields: {list(output.keys())}")
            logger.info("=" * 80 + "\n")
        
        return output
    

    # def _extract_value(self, source: str, data: Dict[str, Any]) -> Any:
    #     if "." not in source:
    #         return source
        
    #     parts = source.split(".")
    #     value = data
        
    #     for part in parts:
    #         logger.debug(f"Accessing part: {part}, current value: {value}")
    #         if isinstance(value, dict):
    #             value = value.get(part)
    #         elif isinstance(value, list) and part.isdigit():
    #             idx = int(part)
    #             value = value[idx] if 0 <= idx < len(value) else None
    #         else:
    #             logger.warning(f"Cannot access {part} on {type(value)}")
    #             return None
            
    #         if value is None:
    #             logger.warning(f"Value is None after accessing {part}")
    #             return None
        
    #     logger.debug(f"Extracted value: {value}")
    #     return value
    DEBUG_EXTRACTION = True  
    def _extract_value(self, source: str, data: Dict[str, Any]) -> Any:
        """
        Extract value from nested dict/list using dot notation with array indices.
        Supports:
            - "node-1.0.metadata.subject" (numeric segment as list index)
            - "output[0].metadata.subject" (bracket notation)
            - "node-1.metadata.subject" (regular dict keys)
        """
        if self.DEBUG_EXTRACTION:
            logger.info(f"=" * 80)
            logger.info(f"EXTRACTION STARTED for source: '{source}'")
            logger.info(f"Available data keys: {list(data.keys()) if isinstance(data, dict) else 'Not a dict'}")
            logger.info(f"Data structure: {type(data)}")
        
        # Handle non-path sources (literal values)
        if "." not in source:
            if self.DEBUG_EXTRACTION:
                logger.info(f"No dots found in source, returning literal: '{source}'")
            return source
        
        parts = source.split(".")
        value = data
        
        if self.DEBUG_EXTRACTION:
            logger.info(f"Split source into {len(parts)} parts: {parts}")
        
        for idx, part in enumerate(parts):
            if self.DEBUG_EXTRACTION:
                logger.info(f"\n--- Processing Part {idx + 1}/{len(parts)}: '{part}' ---")
                logger.info(f"Current value type: {type(value)}")
                
                # Show preview of current value
                if isinstance(value, dict):
                    logger.info(f"Current dict keys: {list(value.keys())}")
                elif isinstance(value, list):
                    logger.info(f"Current list length: {len(value)}")
                    if len(value) > 0:
                        logger.info(f"First item type: {type(value[0])}")
                else:
                    logger.info(f"Current value: {str(value)[:200]}...")
            
            # Check if part has bracket notation like "output[0]"
            match = re.match(r"^(\w+)\[(\d+)\]$", part)
            if match:
                key = match.group(1)
                index = int(match.group(2))
                
                if self.DEBUG_EXTRACTION:
                    logger.info(f"Detected bracket notation: key='{key}', index={index}")
                
                # First access the key
                if isinstance(value, dict):
                    if key in value:
                        value = value.get(key)
                        if self.DEBUG_EXTRACTION:
                            logger.info(f"✓ Successfully accessed key '{key}'")
                            logger.info(f"  Value type after key access: {type(value)}")
                    else:
                        logger.error(f"✗ Key '{key}' not found in dict. Available keys: {list(value.keys())}")
                        return None
                else:
                    logger.error(f"✗ Cannot access key '{key}' on {type(value)}")
                    return None
                
                if value is None:
                    logger.error(f"✗ Value is None after accessing key: {key}")
                    return None
                
                # Then access the index
                if isinstance(value, list):
                    if 0 <= index < len(value):
                        value = value[index]
                        if self.DEBUG_EXTRACTION:
                            logger.info(f"✓ Successfully accessed index [{index}]")
                            logger.info(f"  Value type after index access: {type(value)}")
                    else:
                        logger.error(f"✗ Index [{index}] out of range for list of length {len(value)}")
                        return None
                else:
                    logger.error(f"✗ Cannot access index [{index}] on {type(value)}, expected list")
                    return None
            
            # Check if part is a pure number (list index)
            elif part.isdigit():
                index = int(part)
                
                if self.DEBUG_EXTRACTION:
                    logger.info(f"Detected numeric index: {index}")
                
                if isinstance(value, list):
                    if 0 <= index < len(value):
                        value = value[index]
                        if self.DEBUG_EXTRACTION:
                            logger.info(f"✓ Successfully accessed list index {index}")
                            logger.info(f"  Value type: {type(value)}")
                            if isinstance(value, dict):
                                logger.info(f"  Dict keys: {list(value.keys())}")
                    else:
                        logger.error(f"✗ Index {index} out of range. List length: {len(value)}")
                        return None
                else:
                    logger.error(f"✗ Cannot access index {index} on {type(value)}, expected list")
                    if isinstance(value, dict):
                        logger.error(f"  Available dict keys: {list(value.keys())}")
                    return None
            
            # Regular dict key access
            else:
                if self.DEBUG_EXTRACTION:
                    logger.info(f"Attempting regular dict key access: '{part}'")
                
                if isinstance(value, dict):
                    if part in value:
                        value = value.get(part)
                        if self.DEBUG_EXTRACTION:
                            logger.info(f"✓ Successfully accessed key '{part}'")
                            logger.info(f"  Value type: {type(value)}")
                            if value is not None:
                                preview = str(value)[:200]
                                logger.info(f"  Value preview: {preview}...")
                    else:
                        logger.error(f"✗ Key '{part}' not found in dict")
                        logger.error(f"  Available keys: {list(value.keys())}")
                        return None
                else:
                    logger.error(f"✗ Cannot access key '{part}' on {type(value)}, expected dict")
                    return None
            
            if value is None:
                logger.error(f"✗ Value is None after accessing part: '{part}'")
                return None
        
        if self.DEBUG_EXTRACTION:
            logger.info(f"\n{'=' * 80}")
            logger.info(f"✓ EXTRACTION SUCCESSFUL")
            logger.info(f"Final value type: {type(value)}")
            if isinstance(value, (str, int, float, bool)):
                logger.info(f"Final value: {value}")
            elif isinstance(value, (dict, list)):
                logger.info(f"Final value size: {len(value)}")
            logger.info(f"{'=' * 80}\n")
        
        return value
        
    def _apply_transforms(self, value: Any, transform_str: str) -> Any:
        """Apply transformation(s) using registered strategies"""
        transforms = self._parse_transform_chain(transform_str)
        
        for func_name, args in transforms:
            strategy = self.registry.get(func_name)
            if strategy:
                value = strategy.transform(value, *args)
            else:
                logger.warning(f"Unknown transform: {func_name}")
        
        return value
    
    def _parse_transform_chain(self, transform_str: str) -> List[tuple]:
        """Parse transformation chain into (function, args) tuples"""
        transforms = []
        parts = transform_str.split(".")
        
        for part in parts:
            if not part:
                continue
            
            match = re.match(r"(\w+)\((.*?)\)(\[.*?\])?", part)
            
            if match:
                func_name = match.group(1)
                args_str = match.group(2)
                index_str = match.group(3)
                
                args = []
                
                if args_str:
                    args_str = args_str.strip()
                    if args_str.startswith(("'", '"')):
                        args.append(args_str.strip("'\""))
                
                if index_str:
                    index = int(index_str.strip("[]"))
                    args.append(index)
                
                transforms.append((func_name, args))
        
        return transforms


