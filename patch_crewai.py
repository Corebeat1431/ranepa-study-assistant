import os
import re
import sys

def patch_crewai():
    try:
        import crewai
    except ImportError:
        print("[PATCH-CREWAI] CrewAI is not installed in the current environment.")
        return False

    converter_file = os.path.join(
        os.path.dirname(crewai.__file__),
        "utilities",
        "converter.py"
    )

    if not os.path.exists(converter_file):
        print(f"[PATCH-CREWAI] Could not find converter.py at {converter_file}")
        return False

    print(f"[PATCH-CREWAI] Found converter.py at {converter_file}")

    with open(converter_file, "r", encoding="utf-8") as f:
        content = f.read()

    # Проверяем, применен ли уже патч
    if "Agent or LLM must be provided if converter_cls is not specified." in content:
        print("[PATCH-CREWAI] Patch is already applied.")
        return True

    # 1. Замена ValidationError перехвата в _coerce_response_to_pydantic
    t1 = """        except ValidationError:
            partial = handle_partial_json(
                result=response,
                model=self.model,
                is_json_output=False,
                agent=None,
            )"""
    r1 = """        except ValidationError:
            partial = handle_partial_json(
                result=response,
                model=self.model,
                is_json_output=False,
                agent=None,
                llm=self.llm,
            )"""

    # 2. Замена сигнатуры handle_partial_json
    t2 = """def handle_partial_json(
    result: str,
    model: type[BaseModel],
    is_json_output: bool,
    agent: Agent | BaseAgent | None,
    converter_cls: type[Converter] | None = None,
) -> dict[str, Any] | BaseModel | str:"""
    r2 = """def handle_partial_json(
    result: str,
    model: type[BaseModel],
    is_json_output: bool,
    agent: Agent | BaseAgent | None,
    converter_cls: type[Converter] | None = None,
    llm: Any = None,
) -> dict[str, Any] | BaseModel | str:"""

    # 3. Замена вызова convert_with_instructions в handle_partial_json при JSONDecodeError
    t3 = """        except json.JSONDecodeError:
            return convert_with_instructions(
                result=result,
                model=model,
                is_json_output=is_json_output,
                agent=agent,
                converter_cls=converter_cls,
            )"""
    r3 = """        except json.JSONDecodeError:
            return convert_with_instructions(
                result=result,
                model=model,
                is_json_output=is_json_output,
                agent=agent,
                converter_cls=converter_cls,
                llm=llm,
            )"""

    # 4. Замена финального вызова convert_with_instructions в handle_partial_json
    t4 = """    return convert_with_instructions(
        result=result,
        model=model,
        is_json_output=is_json_output,
        agent=agent,
        converter_cls=converter_cls,
    )"""
    r4 = """    return convert_with_instructions(
        result=result,
        model=model,
        is_json_output=is_json_output,
        agent=agent,
        converter_cls=converter_cls,
        llm=llm,
    )"""

    # 5. Замена сигнатуры convert_with_instructions
    t5 = """def convert_with_instructions(
    result: str,
    model: type[BaseModel],
    is_json_output: bool,
    agent: Agent | BaseAgent | None,
    converter_cls: type[Converter] | None = None,
) -> dict[str, Any] | BaseModel | str:"""
    r5 = """def convert_with_instructions(
    result: str,
    model: type[BaseModel],
    is_json_output: bool,
    agent: Agent | BaseAgent | None,
    converter_cls: type[Converter] | None = None,
    llm: Any = None,
) -> dict[str, Any] | BaseModel | str:"""

    # 6. Замена тела convert_with_instructions
    t6 = """    if agent is None:
        raise TypeError("Agent must be provided if converter_cls is not specified.")

    llm = getattr(agent, "function_calling_llm", None) or agent.llm

    if llm is None:
        raise ValueError("Agent must have a valid LLM instance for conversion")

    instructions = get_conversion_instructions(model=model, llm=llm)
    converter = create_converter(
        agent=agent,
        converter_cls=converter_cls,
        llm=llm,
        text=result,
        model=model,
        instructions=instructions,
    )"""
    r6 = """    if agent is None and llm is None:
        raise TypeError("Agent or LLM must be provided if converter_cls is not specified.")

    if llm is None:
        llm = getattr(agent, "function_calling_llm", None) or agent.llm

    if llm is None:
        raise ValueError("Agent must have a valid LLM instance for conversion")

    instructions = get_conversion_instructions(model=model, llm=llm)
    if agent:
        converter = create_converter(
            agent=agent,
            converter_cls=converter_cls,
            llm=llm,
            text=result,
            model=model,
            instructions=instructions,
        )
    else:
        cls = converter_cls or Converter
        converter = cls(
            llm=llm,
            text=result,
            model=model,
            instructions=instructions,
        )"""

    # Применяем замены
    replacements = [(t1, r1), (t2, r2), (t3, r3), (t4, r4), (t5, r5), (t6, r6)]
    patched_content = content
    for target, replacement in replacements:
        # Нормализуем перенос строк для кроссплатформенности
        target_norm = target.replace("\r\n", "\n")
        replacement_norm = replacement.replace("\r\n", "\n")
        patched_content_norm = patched_content.replace("\r\n", "\n")
        
        if target_norm in patched_content_norm:
            patched_content = patched_content_norm.replace(target_norm, replacement_norm)
        else:
            # Попробуем без нормализации
            if target in patched_content:
                patched_content = patched_content.replace(target, replacement)
            else:
                print(f"[PATCH-CREWAI] Warning: Could not find target code block for replacement:\n{target[:100]}...")

    if patched_content == content:
        print("[PATCH-CREWAI] Error: Content was not modified. No replacements matched.")
        return False

    with open(converter_file, "w", encoding="utf-8") as f:
        f.write(patched_content)

    print("[PATCH-CREWAI] Successfully patched crewai/utilities/converter.py!")
    return True

if __name__ == "__main__":
    success = patch_crewai()
    sys.exit(0 if success else 1)
