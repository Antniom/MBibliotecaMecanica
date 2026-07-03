import os
import fitz

def create_test_files():
    input_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "entrada")
    os.makedirs(input_dir, exist_ok=True)

    # 1. Create a Native PDF (with text layer)
    native_path = os.path.join(input_dir, "Ficha 1 - Resistencia dos Materiais.pdf")
    doc_native = fitz.open()
    page = doc_native.new_page(width=595, height=842) # A4 size
    text_content = (
        "Universidade do Minho / IPLeiria - Engenharia Mecanica\n"
        "Unidade Curricular: Resistencia dos Materiais\n"
        "Ficha de Exercicios 1 - Flexao de Vigas\n\n"
        "Exercicio 1:\n"
        "Considere uma viga simplesmente apoiada submetida a uma carga distribuida uniforme q = 5 kN/m.\n"
        "O comprimento da viga e L = 2 m. Calcule o momento fletor maximo M_max.\n"
        "Formula:\n"
        "M_max = q * L^2 / 8\n\n"
        "Exercicio 2:\n"
        "Determine a tensao normal maxima sabendo que o modulo de flexao W_z = 200 cm^3.\n"
    )
    # Insert text block
    page.insert_text((50, 80), text_content, fontsize=11, lineheight=1.5)
    doc_native.save(native_path)
    doc_native.close()
    print(f"Created native test PDF: {native_path}")

    # 2. Create a Scanned PDF (image-only, representing scan/handwritten notes)
    scanned_path = os.path.join(input_dir, "Resolucao Teste 1 - Mecanica Aplicada (Scanned).pdf")
    doc_temp = fitz.open()
    page_temp = doc_temp.new_page(width=595, height=842)
    scanned_text = (
        "Mecanica Aplicada - Resolucao do Teste 1 (2024)\n"
        "Nome: Joao Silva\n\n"
        "Exercicio 1:\n"
        "Dados: F = 100 N, d = 0.5 m.\n"
        "Momento de uma forca em relacao ao ponto O:\n"
        "M = F * d = 100 * 0.5 = 50 N.m\n"
        "Sentido de rotacao: horario (-)\n"
    )
    page_temp.insert_text((50, 80), scanned_text, fontsize=12, lineheight=1.6)
    
    # Render page to image
    pix = page_temp.get_pixmap(dpi=150)
    img_data = pix.tobytes("png")
    doc_temp.close()

    # Create new PDF and insert the image
    doc_scanned = fitz.open()
    page_scan = doc_scanned.new_page(width=595, height=842)
    rect = fitz.Rect(0, 0, 595, 842)
    page_scan.insert_image(rect, stream=img_data)
    doc_scanned.save(scanned_path)
    doc_scanned.close()
    print(f"Created scanned test PDF: {scanned_path}")

if __name__ == "__main__":
    create_test_files()
