# -*- encoding: utf-8 -*-

# use following CLI command:
# python3.10 ai_aktuell_scraper.py -p AI_Aktuell -s AI_Aktuell_clean

# import necessary modules
import argparse
import os
from tika import parser
import pdftotree
import xml.etree.ElementTree as ET
from pdf_parser import tika_parse
import pdftotree
import re
from typing import List, Tuple
import json


arg_parser = argparse.ArgumentParser(description="extract Text from PDF-files")
arg_parser.add_argument("-p", "--path_to_data", type=str, help="path to the folder containing PDFs")
arg_parser.add_argument("-s", "--save_folder", type=str, help="name of the folder where the text is to be saved")

args = arg_parser.parse_args()


PATH_TO_DATA = "/home/admin1/tb_tool/scraping_data/"+args.path_to_data # Gerichtname
SAVE_PATH = "/home/admin1/tb_tool/clean_scraper_data/"+args.save_folder # Gerichtname_clean


absatz_pattern = r"^(\s)?[0-9]+\.([0-9]+(\.)?)*(\s-\s[0-9]+\.([0-9]+(\.)?)*)?"
absatz_pattern2 = r"^(\s)?[0-9]+\.([0-9]+(\.)?)*(\s-\s[0-9]+\.([0-9]+(\.)?)*)?\s-\s[0-9]+\.([0-9]+(\.)?)*(\s-\s[0-9]+\.([0-9]+(\.)?)*)?"
absatz_pattern3 = r"(\d{1,3}((\.\s)|([a-z]{1,3}\)\.?)|(\s[a-z]\)))|§.*:|[a-z]{1,2}\)(\s[a-z]{1,2}\))?|\d{1,3}\.|(^I{1,3})?V?X?\.)"
datum_pattern = r"[0-9][0-9]?\.([\s]{1,2}([A-Z][a-z]+|März)|[0-9]{1,2}\.)\s?[1-9][0-9]{3}|[0-9]{1,2}\.,"
false_marks = []

def split_lines(parsed_text: str) -> List[str]:
    split_lines = [line.strip().replace("     ", " ").replace("\uf02d", "") for line in parsed_text.split("\n")]
    return split_lines


def get_pages(lines: List[str]) -> str:
    page_pattern = r"^[1-9]{1,2}\s[-–]\s[0-9]{1,2}"
    pages = [lines.pop(lines.index(line)) for line in lines if re.fullmatch(page_pattern, line)]
    if pages:
        return pages[0].replace(" ", "")
    else:
        return ""


def get_footnotes(lines: List[str]) -> List[Tuple[str]]:
    footnotes = []
    for i, fn in enumerate(lines):
        if fn and fn[0].isdigit() and fn[-1].isdigit() and not lines[i-1]:
            counter = 1
            fn_parts = []
            while not lines[i+counter].endswith("."):
                fn_parts.append(lines[i+counter])
                lines[i+counter] = ""
                counter += 1
            fn_parts.append(lines[i+counter])
            lines[i + counter] = ""
            fn_parts = [line.strip("-") for line in fn_parts] # removes trailing hyphens
            footnotes.append((lines[i], "".join(fn_parts)))
            lines[i] = ""
    return footnotes


def get_paras(lines: List[str]) -> List[str]:
    clean_lines = []
    para = ""
    pattern_to_skip = 'anonymisierter Entscheid für Publikation - löst keine RM aus und führ Geschäft nicht nach'
    for i, line in enumerate(lines[:-1]):
        # get footnote reference in text
        # if line and line[0].isdigit() and line[-1].isdigit() and lines[i - 1]:
        #     if para:
        #         clean_lines.append(para.strip())
        #         para = ""
        #     clean_lines.append(line)

        # match pure paragraph numbers
        if (re.fullmatch(absatz_pattern, line) or re.fullmatch(absatz_pattern2, line) or re.fullmatch(absatz_pattern3, line)) and not re.fullmatch(datum_pattern, line):
            if para:
                clean_lines.append(para.strip())
                para = ""
            clean_lines.append(line)

        # match paragraph numbers with additional text and split
        elif (re.match(absatz_pattern, line) or re.match(absatz_pattern2, line) or re.match(absatz_pattern3, line)) and not re.match(datum_pattern, line) and not line.endswith("Kammer"):
            line = line.split(" ", 1)
            if para:
                clean_lines.append(para.strip())
                para = ""
            clean_lines.append(line[0])
            # print(line)
            if line[1].endswith("-") or line[1].endswith("–"): 
                para += line[1][:-1]
            else:
                para += line[1] + " "

        # remove links which are not visible in pdf
        elif line.startswith("http"):
            continue

        # remove hyphens at the end of lines if next text is lowercased
        elif line and line != pattern_to_skip:
            if line.endswith("-") or line.endswith("–"):# and lines[i+2] and line[i+2][0].islower():
                para += line[:-1]
            else:
                para += line+" "

    # if para is not an empty string it is appended to the clean_lines list
    if para:
        clean_lines.append(para.strip())
        para = ""
    return clean_lines


def build_xml_tree(filename: str, loaded_json, filter_list: List, pages: str, footnotes=[]):
    """Build an XML-tree."""
    text_node = ET.Element("text")
    text_node.attrib["id"] = filename[:-4]
    text_node.attrib["author"] = ""
    if "Kopfzeile" in loaded_json.keys():
        text_node.attrib["title"] = loaded_json["Kopfzeile"][0]["Text"].strip()
        text_node.attrib["source"] = "https://entscheidsuche.ch"
    if "Seiten" in loaded_json.keys():
        text_node.attrib["page"] = pages
    elif "Abstract" in loaded_json.keys() and "S." in loaded_json["Abstract"][0]["Text"]:
        index = loaded_json["Abstract"][0]["Text"].find("S.")+3
        colon_index = loaded_json["Abstract"][0]["Text"].find(":")
        text_node.attrib["page"] = loaded_json["Abstract"][0]["Text"][index:colon_index]
    else:
        text_node.attrib["page"] = ""
    if "Meta" in loaded_json.keys():
        text_node.attrib["topics"] = loaded_json["Meta"][0]["Text"][:-1]
    else:
        text_node.attrib["topics"] = ""
    text_node.attrib["subtopics"] = ""
    if "Sprache" in loaded_json.keys():
        text_node.attrib["language"] = loaded_json["Sprache"].replace('  ', ' ')
    else:
        text_node.attrib["language"] = loaded_json["Meta"][0]["Sprachen"][0]
    if filename.endswith("nodate.html"):
        text_node.attrib["date"] = "0000-00-00"
    else:
        text_node.attrib["date"] = loaded_json["Datum"].replace('  ', ' ')
    if "Abstract" in loaded_json.keys():
        text_node.attrib["description"] = loaded_json["Abstract"][0]["Text"]
    else:
        text_node.attrib["description"] = loaded_json["Kopfzeile"][0]["Text"]
    text_node.attrib["type"] = loaded_json["Signatur"].replace('  ', ' ')
    text_node.attrib["file"] = filename
    if filename.endswith("nodate.html"):
        text_node.attrib["year"] = "0000"
    else:
        if "-" in loaded_json["Datum"]:
            text_node.attrib["year"] = loaded_json["Datum"][:4]
        else:
            text_node.attrib["year"] = loaded_json["Datum"][-4:]
    if filename.endswith("nodate.html"):
        text_node.attrib["decade"] = "0000-00-00"
    else:
        if "-" in loaded_json["Datum"]:
            text_node.attrib["decade"] = loaded_json["Datum"][:3] + "0"
        else:
            text_node.attrib["decade"] = loaded_json["Datum"][-4:-1] + "0"
    if "HTML" in loaded_json.keys():
        text_node.attrib["url"] = loaded_json["HTML"]["URL"].replace('  ', ' ')
    # body node with paragraph nodes
    # header_node = ET.SubElement(text_node, "header") # drinlassen?
    body_node = ET.SubElement(text_node, "body")
    for para in filter_list:
        p_node = ET.SubElement(body_node, "p")
        if para in false_marks:
            p_node.attrib["type"] = "plain_text"
        elif re.match(datum_pattern, para):
            p_node.attrib["type"] = "plain_text"
        elif footnotes and para.isdigit():
            fn_node = ET.SubElement(p_node, "fn")
            for num, fn in footnotes:
                if num == para:
                    fn_node.text = f"{num}, {fn}"
            continue
        elif re.fullmatch(absatz_pattern3, para) or re.fullmatch(absatz_pattern2, para) or re.fullmatch(absatz_pattern, para):
            p_node.attrib["type"] = "paragraph_mark"
        elif para.startswith("<table"):
            p_node.attrib["type"] = "table"
        else:
            p_node.attrib["type"] = "plain_text"
        p_node.text = para
    tree = ET.ElementTree(text_node) # creating the tree
    return tree



def main():
    for filename in sorted(os.listdir(PATH_TO_DATA)):
        if filename.endswith("pdf") and filename[:-4] + ".xml":
            print(f"The following file is being processed:\n{os.path.join(PATH_TO_DATA, filename)}\n")
            # parse with tika library from separate script
            parsed_text = tika_parse(os.path.join(PATH_TO_DATA, filename))
            # parse with pdftotree library
            # tree = pdftotree.parse(os.path.join(PATH_TO_DATA, filename))
            # print(tree)
            # root = ET.fromstring(tree)
            # for div in root.iter("div"):
            #     if div.attrib["class"] == "ocrx_block":
            #         for span in div.iter("span"):
            #             print(span.text)
            lines = split_lines(parsed_text)
            pages = get_pages(lines)
#             footnotes = get_footnotes(lines)
            clean_text = get_paras(lines)

            # create new filenames for the xml files
            if filename.endswith("nodate.html"):
                xml_filename = filename.replace("nodate.html", "0000-00-00.xml")
            else:
                xml_filename = filename[:-4] + ".xml"

            # open json pendant
            json_name = filename[:-3]+"json"
            if json_name in sorted(os.listdir(PATH_TO_DATA)):
                with open(os.path.join(PATH_TO_DATA, json_name), "r", encoding="utf-8") as json_file:
                    loaded_json = json.load(json_file)  # load json
                    tree = build_xml_tree(filename, loaded_json, clean_text, pages)  # generates XML tree # footnotes argument removed here bc no fn in text
                    tree.write(os.path.join(SAVE_PATH, xml_filename), encoding="UTF-8", xml_declaration=True)  # writes tree to file
                    ET.dump(tree)  # shows tree in console
            # print(parsed_text)
            # print(lines)
            # print(pages)
#             print(footnotes)
#             print(clean_text)



        print("\n===========================================================\n\n")


if __name__ == "__main__":
    main()
