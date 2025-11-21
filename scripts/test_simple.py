import os
from llama_cpp import Llama
from llama_cpp.llama_chat_format import Llava15ChatHandler

chat_handler = Llava15ChatHandler(clip_model_path="./models/llava-v1.5/mmproj-model-f16.gguf")

llm = Llama(
    model_path="./models/llava-v1.5/ggml-model-q4_k.gguf",
    chat_handler=chat_handler,
    use_mmap=True,
    n_threads=os.cpu_count(),
    n_batch=512,
    use_mlock=False,
    verbose=True,
    n_ctx=4096,  # n_ctx should be increased to accommodate the image embedding
)

import base64


def image_to_base64_data_uri(file_path):
    with open(file_path, "rb") as img_file:
        base64_data = base64.b64encode(img_file.read()).decode("utf-8")
        return f"data:image/jpeg;base64,{base64_data}"


# Replace 'file_path.png' with the actual path to your PNG file
file_path = "./data/obra_casa.jpeg"
data_uri = image_to_base64_data_uri(file_path)

prompt = """
You must analyze only what is 100% visible in the image, with zero inference and zero assumptions.
If any detail is unclear, partially cropped, ambiguous, or not possible to confirm, answer:
“It is not possible to determine precisely.”

Answer strictly and only the questions below, in one continuous paragraph:

Which structural walls are visible?

Which columns or vertical load-bearing elements are visible?

Which beams, slabs, roof edges, or overhangs are visible?

Which openings (doors, windows, vents) are visible?

Which ground-level elements are visible (ramp, pavement, markings, steps)?

Which façade elements or architectural volumes are visible?

Which external mechanical/electrical elements are visible (if any)?

Which vegetation or landscaping elements are visible (only if 100% clear)?

Rules:

No assumptions about function or materials.

No invented elements or hallucinations.

No interpretation of interior spaces.

No descriptions outside the frame.

No soft language (“seems,” “appears,” etc.).

Describe only what can be visually confirmed.

Task:
Provide one single paragraph answering only the eight questions above, with maximum structural detail and zero inference.
"""


# Chamada de API com as melhorias para análise arquitetônica:
output = llm.create_chat_completion(
    messages=[
        #{"role": "system", "content": system_prompt},
        {
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": data_uri}},
            ],
        },
    ],
    temperature=0,
    top_k=2,
    top_p=1,
    max_tokens=4096,
    repeat_penalty=1.0,
)
print(output)
