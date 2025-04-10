import json
import time
import os
import base64
import mimetypes
import requests
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.wait import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from dotenv import load_dotenv

load_dotenv()

class CaptchaSolver:
    def __init__(self):
        self.URL_GEMINI = os.getenv("URL_GEMINI")
        self.URL_FGTS = os.getenv("URL_FGTS")
        self.API_KEY_GEMINI = os.getenv("API_KEY_GEMINI")

    def configure_chrome_for_pdf(self):
        # Configurações para salvar o PDF automaticamente
        options = Options()

        # Define o diretório de "Documents" para o sistema operacional atual
        if os.name == 'nt':  # Windows
            download_dir = os.path.join(os.environ['USERPROFILE'], 'Documents', 'certificados')
        else:  # Unix-based (Linux/macOS)
            download_dir = os.path.join(os.path.expanduser('~'), 'Documents', 'certificados')

        # Cria o diretório caso não exista
        if not os.path.exists(download_dir):
            os.makedirs(download_dir)

        # Definindo as preferências do Chrome para download de PDFs
        prefs = {
            "printing.print_preview_sticky_settings": False,
            "savefile.default_directory": download_dir,  # Diretório onde o PDF será salvo
            "download.default_directory": download_dir,  # Diretório onde o PDF será salvo
            "safebrowsing.enabled": "true",
            "disable-popup-blocking": True,
            "print.always_print_silent": True,  # Faz a impressão sem exibir a caixa de diálogo
            "print.show_print_progress": False,
        }
        options.add_experimental_option("prefs", prefs)

        #options.add_argument("--kiosk-printing")
        #options.add_argument("--headless=new")

        # Inicializa o navegador com as preferências definidas
        driver = webdriver.Chrome(options=options)
        return driver

    def capture_captcha(self):
        browser = webdriver.Chrome()
        browser.get(self.URL_FGTS)

        try:
            captcha_img = WebDriverWait(browser, 10).until(
                EC.presence_of_element_located((By.ID, "captchaImg_N2"))
            )
            time.sleep(2)

            captcha_path = "captchas/captcha.png"
            if not os.path.exists("captchas"):
                os.makedirs("captchas")

            captcha_img.screenshot(captcha_path)

            return captcha_path, browser

        except Exception as e:
            print(f"Erro ao capturar captcha: {e}")
            browser.quit()
            return None, None

    def send_for_analysis(self, path_image):
        prompt = """
        Por favor, extraia o texto da imagem fornecida. Crie um JSON com a seguinte estrutura:

        - 'is_extract': (valor booleano) 'true' caso o texto tenha sido extraído corretamente, 'false' caso contrário.
        - 'captcha': (campo de texto) O texto extraído da imagem.

        Instruções adicionais:
        1. Se houver caracteres que podem ser confundidos, como '0' (zero) e 'O', 'o' (minúsculo) e 'O' (maiúsculo), '2' e 'Z', ou quaisquer outros números e letras similares, considere o contexto da imagem para distinguir corretamente entre eles.
        2. Se não houver clareza sobre qual caractere é o correto (por exemplo, '0' ou 'O'), indique no valor de 'captcha' o que parece mais provável, mas sem fazer suposições não fundamentadas.
        3. Certifique-se de que o texto extraído está o mais fiel possível ao que está na imagem, evitando qualquer confusão de caracteres visualmente similares.
        4. Em hipótese alguma traga pontuações como texto extraido, nenhuma imagem vem com pontuaçãos, apenas números e letras.

        Essa abordagem ajuda a garantir que as confusões entre caracteres similares sejam minimizadas e que o resultado final seja mais preciso.
        """
        with open(path_image, "rb") as img_file:
            base64_image = base64.b64encode(img_file.read()).decode("utf-8")
            mime_type, _ = mimetypes.guess_type(path_image)
            mime_type = mime_type if mime_type else "image/png"

            headers = {
                "Content-Type": "application/json"
            }

            payload = {
                "contents": [
                    {
                        "role": "user",
                        "parts": [
                            {
                                "inlineData": {
                                    "mimeType": mime_type,
                                    "data": base64_image
                                }
                            },
                            {
                                "text": prompt
                            }
                        ]
                    }
                ],
                "generationConfig": {
                    "responseMimeType": "text/plain"
                }
            }
            response = requests.post(
                f"{self.URL_GEMINI}?key={self.API_KEY_GEMINI}",
                headers=headers,
                json=payload
            )

            if response.status_code != 200:
                print("Erro ao enviar imagem para análise:", response.status_code)
                return None

            #print("Resposta do servidor:", response.text)

            return response.json()

    def process_response(self, response):
        if response is None:
            print("Erro ao processar a resposta do servidor.")
            return None
        print(response)
        try:
            text = response["candidates"][0]["content"]["parts"][0]["text"]
            print("Texto retornado:", text)
            # Limpa formatação Markdown, se houver
            if text.startswith("```json"):
                text = text.replace("```json", "").replace("```", "").strip()

            # Converte o JSON de string para dicionário
            dados = json.loads(text)

            # Captura os campos desejados
            is_extract = dados.get("is_extract")
            captcha = dados.get("captcha")

            return is_extract, captcha

        except Exception as e:
            print("Erro ao extrair dados da resposta:", e)
            return None, None

    def main(self, CNPJ):
        captcha_path, browser = self.capture_captcha()

        if captcha_path:
            response = self.send_for_analysis(captcha_path)

            is_extract, text = self.process_response(response)

            if text == "Codigo2" or text == "null":
                print("Encerrando navegador.")
                browser.quit()
                exit()

            if is_extract:
                try:
                    WebDriverWait(browser, 10).until(
                        EC.presence_of_element_located((By.ID, "mainForm:txtCaptcha"))
                    )

                    browser.find_element(By.ID, "mainForm:txtInscricao1").send_keys(CNPJ)
                    browser.find_element(By.ID, "mainForm:txtCaptcha").send_keys(text)
                    browser.find_element(By.XPATH, '//*[@id="mainForm:btnConsultar"]').click()

                    WebDriverWait(browser, 10).until(
                        EC.presence_of_element_located((By.ID, "mainForm:j_id51"))
                    )

                    browser.find_element(By.XPATH, '//*[@id="mainForm:j_id51"]').click()

                    WebDriverWait(browser, 10).until(
                        EC.presence_of_element_located((By.ID, "mainForm:btnVisualizar"))
                    )

                    browser.find_element(By.XPATH, '//*[@id="mainForm:btnVisualizar"]').click()

                    WebDriverWait(browser, 10).until(
                        EC.presence_of_element_located((By.XPATH, '//*[@id="mainForm"]/table[2]'))
                    )

                    pdf = browser.execute_cdp_cmd("Page.printToPDF", {
                        "printBackground": True
                    })

                    # Salva o conteúdo como PDF
                    output_path = os.path.join("pdfs_salvos", f"{CNPJ}_certificado.pdf")
                    if not os.path.exists("pdfs_salvos"):
                        os.makedirs("pdfs_salvos")

                    with open(output_path, "wb") as f:
                        f.write(base64.b64decode(pdf['data']))

                    print(f"PDF salvo automaticamente em: {output_path}")
                except Exception as e:
                    print(f"Erro ao aguardar remoção do captcha ou carregamento das novas páginas: {e}")
                    browser.quit()
                    exit()
            else:
                print("Não foi possível extrair o texto do captcha.")

            browser.quit()
        else:
            print("Erro ao capturar o captcha.")


if __name__ == "__main__":
    CNPJ = ""
    captcha_solver = CaptchaSolver()
    captcha_solver.main(CNPJ)