import argparse
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup



def get_all_match_ids(url):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
        )
        page = context.new_page()
        
        print(f"Loading page: {url}")
        page.goto(url, wait_until="domcontentloaded")
        
        print("Waiting 8 seconds for widget to render...")
        page.wait_for_timeout(8000) 
        
        html_content = page.content()
        browser.close()

    print("Parsing HTML...")
    soup = BeautifulSoup(html_content, "html.parser")
    match_elements = soup.find_all("tbody", attrs={"data-match": True})
    
    match_ids = []
    for element in match_elements:
        match_id = element.get("data-match")
        if match_id and match_id not in match_ids:
            match_ids.append(match_id)
            
    return match_ids

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True, help="URL of the Opta player stats widget page")
    parser.add_argument("--output", required=True, help="Path to write the output match IDs text file")
    args = parser.parse_args()

    ids = get_all_match_ids(args.url)
    print(f"\nExtracted {len(ids)} Match IDs.")

    with open(args.output, "w", encoding="utf-8") as f:
        for match_id in ids:
            f.write(f'"{match_id}",\n')

    print(f"Successfully saved match IDs to '{args.output}'.")

if __name__ == "__main__":
    main()