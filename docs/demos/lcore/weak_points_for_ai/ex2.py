# weak API, can be fixed a bit by dynamic dispatch
for part in content:
    part_type = getattr(part, "type", None)
    if part_type == "input_text":
        input_text_part = cast(InputTextPart, part)
        if input_text_part.text:
            text_fragments.append(input_text_part.text.strip())
    elif part_type == "output_text":
        output_text_part = cast(OutputTextPart, part)
        if output_text_part.text:
            text_fragments.append(output_text_part.text.strip())
    elif part_type == "refusal":
        refusal_part = cast(ContentPartRefusal, part)
        if refusal_part.refusal:
            text_fragments.append(refusal_part.refusal.strip())
