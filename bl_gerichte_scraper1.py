#!/usr/bin/env python
# coding: utf-8
# scraper for BL_Gerichte

from bs4 import BeautifulSoup
import os
import argparse
from typing import List
import xml.etree.ElementTree as ET
import json
import re
import unicodedata
import glob


parser = argparse.ArgumentParser(description='generate clean XML-files from HTML-files')
parser.add_argument('-p','--path_to_data',type=str,help="directory where all the different data is stored")
parser.add_argument('-d','--directory',type=str,default='BL_Gerichte',help='current directory for the scraper')
parser.add_argument('-t','--type',type=str, default=".html", help="default filetype (html or pdf usually)")

args = parser.parse_args()

PATH_TO_DATA = args.path_to_data

SAVE_PATH = '/home/admin1/tb_tool/clean_scraper_data/BL_Gerichte_clean/'

absatz_pattern = r'^(\s)?[0-9]+\.([0-9]+(\.)?)*(\s-\s[0-9]+\.([0-9]+(\.)?)*)?'
absatz_pattern2 = r'^(\s)?[0-9]+\.([0-9]+(\.)?)*(\s-\s[0-9]+\.([0-9]+(\.)?)*)?\s-\s[0-9]+\.([0-9]+(\.)?)*(\s-\s[0-9]+\.([0-9]+(\.)?)*)?'
datum_pattern = r'[0-9][0-9]?\.[\s]{1,2}([A-Z][a-z]+|März)\s[1-9][0-9]{3}'

false_marks = ['272.8', '268.1', '480.00', '998.67', '442.50', '365.00']

def check_if_duplicate(filename) -> bool:
	"""Check if same file has already been converted.
	Returns True if file exists in destination directory.
	Returns False if file does not yet exist in destination directory."""
	filename = filename.rstrip("nodate.html")
	if glob.glob(SAVE_PATH+filename+"*") != []:
		return True
	else:
		return False


def parse_text(parsed_html, filename) -> List[str]:
	"""Get text out of HTML-files."""
	text = []
	invalid_tags = ['sup', 'br']
	if parsed_html.findAll(['p']):
		for other_tag in parsed_html.findAll(["table", "br", "p"]):
			if other_tag.name == "table":
				text.append(str(other_tag))
			elif other_tag.name == "br":
				text.append("")
			else:
				text.append(unicodedata.normalize('NFKD', other_tag.get_text()).strip("\n         "))
	else:
		text_str = unicodedata.normalize('NFKD', parsed_html.get_text()).strip().replace("          ", "").replace("  ", "")
		text = text_str.split("\n")
		filter_list = list(filter(lambda x: x != "", text))
		filter_list = list(filter(lambda x: x != " ", filter_list))
		filter_list = list(filter(lambda x: x != "   ", filter_list))
		filter_list = list(filter(lambda x: x != "    ", filter_list))
		text = list(filter(lambda x: x != "", filter_list))

	return text


def remove_hyphens(old_text) -> List[str]:
	"""Removes hyphens and merge elements."""
	text_wo_hyphens = []
	for i, para in enumerate(old_text):
		if para.startswith("<table"):
			text_wo_hyphens.append(para)
		para = para.replace('\n', ' ')
		para = para.replace('  ', '')
		para = para.replace('   ', '')
		if para.endswith('-') and not para.endswith('--') and old_text[i+1][0].islower:
			text_wo_hyphens.append(para[:-1]+old_text[i+1].replace('\n              ', ' ').replace('\n             \n             ', ' ').replace('  ', ''))
			del old_text[i+1]
		else:
			text_wo_hyphens.append(para)
	return text_wo_hyphens


def remove_page_breaks(text_wo_hyphens) -> List[str]:
	""""Remove page breaks and merge elements."""
	clean_text_list = []
	listing_pattern = r'[a-z]\)\s?'
	for i, element in enumerate(text_wo_hyphens):
		if element.startswith("<table"):
			clean_text_list.append(element)
		elif i+1 < len(text_wo_hyphens) and text_wo_hyphens[i+1][0].islower() and not re.match(listing_pattern, text_wo_hyphens[i+1]):
			clean_text_list.append(element + ' ' + text_wo_hyphens[i+1])
			del text_wo_hyphens[i]
		elif i+1 < len(text_wo_hyphens) and text_wo_hyphens[i+1].startswith('X.-Weg'):
			clean_text_list.append(element + ' ' + text_wo_hyphens[i+1])
			del text_wo_hyphens[i+1]
		elif element[-1] == '=':
			clean_text_list.append(element + ' ' + text_wo_hyphens[i + 1])
			del text_wo_hyphens[i + 1]
		else:
			clean_text_list.append(element)
	return clean_text_list


def split_absatznr(text_list) -> List[str]:
	"""Split 'paragraph_mark' from rest of the text."""
	paragraph_list = []
	for i, element in enumerate(text_list):
		if element.startswith("<table"):
			paragraph_list.append(element)
		elif element == 'Fr.' and re.match(absatz_pattern, text_list[i+1]):
			paragraph_list.append(element+' '+text_list[i+1])
			del text_list[i+1]
		elif re.search(absatz_pattern2, element):
			match2 = re.search(absatz_pattern2, element).group(0)
			if element.startswith(match2):
				paragraph_list.append(match2)
				paragraph_list.append(element.lstrip(match2))
			elif element == match2:
				paragraph_list.append(element)
			elif element.startswith('(...)'):
				paragraph_list.append('(...)')
				paragraph_list.append(match2)
				paragraph_list.append(element.lstrip('(...)'+match2))
			else:
				paragraph_list.append(element)
		elif re.search(absatz_pattern, element):
			match = re.search(absatz_pattern, element).group(0)
			if element.startswith(match) and text_list[i+1] == 'Mietzins':
				paragraph_list.append(element + ' ' + text_list[i + 1])
				del text_list[i + 1]
			elif element.startswith(match) and not element.startswith(match+'-'):
				paragraph_list.append(match)
				paragraph_list.append(element.lstrip(match))
			elif element.startswith('(...)'):
				paragraph_list.append('(...)')
				paragraph_list.append(match)
				paragraph_list.append(element.lstrip('(...)'+match))
			elif element == match:
				paragraph_list.append(element)
			else:
				paragraph_list.append(element)
		else:
			paragraph_list.append(element)
	return paragraph_list


def iterate_files(directory, filetype):
	# f_list = ["BL_SG_001_2011-30_2011-09-23.html"]
	for filename in sorted(os.listdir(directory)):
		if filename.endswith(filetype): # and filename in f_list:
			fname = os.path.join(directory, filename)
			fname_json = os.path.join(directory, filename[:-5] + '.json')
			if filename.endswith("nodate.html"):
				if not check_if_duplicate(filename):
					xml_filename = filename.replace("nodate.html", "0000-00-00.xml")
				else:
					continue
			else:
				xml_filename = filename[:-5] + ".xml"
			# xml_filename = filename[:-5] + '.xml'
			full_save_name = os.path.join(SAVE_PATH, xml_filename)
			print("Current file name: ", os.path.abspath(fname), 'will be converted into ', xml_filename)
			print('\n')
			with open(fname, 'r', encoding='utf-8') as file:  # open html file for reading
				with open(fname_json, 'r', encoding='utf-8') as json_file:  # open json file for reading
					loaded_json = json.load(json_file)  #load json
					beautifulSoupText = BeautifulSoup(file.read(), 'html.parser')  #read html
					# print(beautifulSoupText)
					# print(extract_table(beautifulSoupText))
					text = parse_text(beautifulSoupText, filename[:-5])
					# print(text)
					filter_list = filter(lambda x: x != "", text)  # removes empty list elements
					filtered_paragraph_list = list(filter_list)
					text_wo_hyphens = remove_hyphens(filtered_paragraph_list)
					# print(text_wo_hyphens)
					# print('\n')
					clean_text_list = remove_page_breaks(text_wo_hyphens)
					# print('\n')
					# print(clean_text_list)
					# print('\n')
					paragraph_list = split_absatznr(clean_text_list)

					# building the xml tree
					# text node with attributes
					text_node = ET.Element('text')
					text_node.attrib['id'] = filename[:-5]
					text_node.attrib['author'] = ''
					if 'Kopfzeile' in loaded_json.keys():
						text_node.attrib['title'] = loaded_json['Kopfzeile'][0]['Text']
					else:
						text_node.attrib['title'] = get_title(beautifulSoupText)
					text_node.attrib['source'] = 'https://entscheidsuche.ch'  # ?
					text_node.attrib['page'] = ''
					if 'Meta' in loaded_json.keys():
						text_node.attrib['topics'] = loaded_json['Meta'][0]['Text']
					else:
						text_node.attrib['topics'] = ''
					text_node.attrib['subtopics'] = ''
					if 'Sprache' in loaded_json.keys():
						text_node.attrib['language'] = loaded_json['Sprache']
					else:
						text_node.attrib['language'] = loaded_json['Kopfzeile'][0]['Sprachen']
					if filename.endswith("nodate.html"):
						text_node.attrib["date"] = "0000-00-00"
						text_node.attrib["year"] = "0000"
						text_node.attrib["decade"] = "0000"
					else:
						text_node.attrib["date"] = loaded_json["Datum"].replace('  ', ' ')
						text_node.attrib["year"] = loaded_json["Datum"][:4]
						text_node.attrib["decade"] = loaded_json["Datum"][:3] + "0"
					text_node.attrib['description'] = loaded_json['Abstract'][0]['Text']
					text_node.attrib['type'] = loaded_json['Signatur']
					text_node.attrib['file'] = filename
					if 'HTML' in loaded_json.keys():
						text_node.attrib['url'] = loaded_json['HTML']['URL']


					# body node with paragraph nodes
					# header_node = ET.SubElement(text_node, 'header') # drinlassen?

					body_node = ET.SubElement(text_node, 'body')
					for para in paragraph_list:
						if para.startswith(' '): # so that random whitespaces in the beginning of paragraphs are deleted
							para = para[1:]
						p_node = ET.SubElement(body_node, 'p')
						if para in false_marks:
							p_node.attrib['type'] = 'plain_text'
						elif re.match(absatz_pattern, para):
							p_node.attrib['type'] = 'paragraph_mark'
						elif para.startswith("<table"):
							p_node.attrib["type"] = "table"
						else:
							p_node.attrib['type'] = 'plain_text'
						p_node.text = para
					# pb_node = ET.SubElement(body_node, 'pb') # drinlassen?
					# footnote_node = ET.SubElement(text_node, 'footnote') # drinlassen?

					# creating/outputting the tree
					tree = ET.ElementTree(text_node)
					tree.write(full_save_name, encoding='UTF-8', xml_declaration=True)  # writes tree to file
					ET.dump(tree)  # shows tree in console
					print('\n\n')



def main():

	iterate_files(PATH_TO_DATA+args.directory, args.type)


if __name__ == '__main__':
	main()