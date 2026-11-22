import argparse
import logging
import re
import sys
from pathlib import Path
from typing import Optional
MAX_READ_BYTES =100 *1024
FILE_EXTENSIONS ={
".py":"Python",
".js":"JavaScript",
".ts":"TypeScript",
".java":"Java",
".cpp":"C++",
".c":"C",
".h":"Заголовок C/C++",
".hpp":"Заголовок С++",
".ino":"Arduino",
".cs":"C#",
".php":"PHP",
".rb":"Ruby",
".go":"Go",
".rs":"Rust",
".swift":"Swift",
".kt":"Kotlin",
".scala":"Scala",
".r":"R",
".m":"Objective-C",
".sql":"SQL",
".html":"HTML",
".css":"CSS",
".scss":"SCSS",
".vue":"Vue",
".jsx":"JSX",
".tsx":"TSX",
".xml":"XML",
".json":"JSON",
".yaml":"YAML",
".yml":"YAML",
".sh":"Shell",
".bat":"Batch",
".ps1":"PowerShell",
".md":"Markdown",
}
def setup_logging (verbose :bool )->None :
    level =logging .DEBUG if verbose else logging .INFO
    logging .basicConfig (
    level =level ,
    format ="%(имя уровня)s: %(сообщение)s",
    stream =sys .stderr ,
    )
def is_binary (content :bytes )->bool :
    if b"\x00"in content :
        return True
    try :
        text =content .decode ("utf-8",errors ="strict")
    except UnicodeDecodeError :
        return True
    non_printable =sum (
    1 for c in text
    if ord (c )<32 and c not in " \n\r\t\x0b\x0c"
    )
    if len (text )>0 and non_printable /len (text )>0.05 :
        return True
    return False
def read_file_head (path :Path ,max_bytes :int =MAX_READ_BYTES )->Optional [str ]:
    try :
        content =path .read_bytes ()
    except (OSError ,PermissionError )as e :
        logging .debug ("Не удалось прочитать %s: %s",path ,e )
        return None
    if len (content )>max_bytes :
        content =content [:max_bytes ]
    if is_binary (content ):
        return None
    try :
        return content .decode ("utf-8",errors ="replace")
    except Exception :
        return None
def extract_description_from_headers (text :str )->Optional [str ]:
    lines =text .split ("\n")
    for line in lines :
        line_stripped =line .strip ()
        if not line_stripped :
            continue
        if line_stripped .startswith ("#")and not line_stripped .startswith ("#!"):
            m =re .match (r"^#+\s+(.+)$",line_stripped )
            if m :
                return m .group (1 ).strip ()
        break
    m =re .search (r'^(?:#![^\n]*\n)?\s*(?:"""|\'\'\')\s*(.+?)(?:"""|\'\'\')',text ,re .DOTALL )
    if m :
        first_line =m .group (1 ).strip ().split ("\n")[0 ].strip ()
        if first_line :
            return first_line
    head =text [:2048 ]
    m =re .search (r"<title[^>]*>(.*?)</title>",head ,re .DOTALL |re .IGNORECASE )
    if m :
        return re .sub (r"\s+"," ",m .group (1 ).strip ())
    m =re .search (r"<h1[^>]*>(.*?)</h1>",head ,re .DOTALL |re .IGNORECASE )
    if m :
        return re .sub (r"\s+"," ",m .group (1 ).strip ())
    return None
def extract_description_from_comments (text :str ,ext :str )->Optional [str ]:
    lines =text .split ("\n")
    for line in lines :
        line_stripped =line .strip ()
        if not line_stripped :
            continue
        if line_stripped .startswith ("#")and not line_stripped .startswith ("#!"):
            return line_stripped .lstrip ("#").strip ()
        if line_stripped .startswith ("//"):
            return line_stripped .lstrip ("/").strip ()
        if line_stripped .startswith ("<!--"):
            m =re .match (r"<!--\s*(.*?)\s*-->",line_stripped ,re .DOTALL )
            if m :
                return m .group (1 ).strip ()
        if re .match (r"^(REM|::)\s+",line_stripped ,re .I ):
            return re .sub (r"^(REM|::)\s+","",line_stripped ,flags =re .I ).strip ()
        if line_stripped .startswith ("/*"):
            m =re .match (r"/\*\*?\s*(.*?)\s*\*/",line_stripped ,re .DOTALL )
            if m :
                return m .group (1 ).strip ().split ("\n")[0 ].strip ()
    block =re .search (r"^/\*\*?\s*(.*?)\s*\*/",text ,re .DOTALL )
    if block :
        first_line =block .group (1 ).strip ().split ("\n")[0 ].strip ()
        if first_line and not first_line .startswith ("*"):
            return first_line .lstrip ("*").strip ()
    return None
def get_file_description (path :Path )->str :
    text =read_file_head (path )
    if not text :
        return ""
    desc =extract_description_from_headers (text )
    if desc :
        if len (desc )>80 :
            desc =desc [:77 ]+"..."
        return desc
    desc =extract_description_from_comments (text ,path .suffix .lower ())
    if desc :
        if len (desc )>80 :
            desc =desc [:77 ]+"..."
        return desc
    return ""
def get_dir_description (dir_path :Path )->str :
    for name in ("README.md","README","index.html","index.php","index.md"):
        candidate =dir_path /name
        if candidate .is_file ():
            text =read_file_head (candidate )
            if text :
                desc =extract_description_from_headers (text )or extract_description_from_comments (
                text ,candidate .suffix .lower ()
                )
                if desc and len (desc )>80 :
                    desc =desc [:77 ]+"..."
                if desc :
                    return desc
    return ""
def normalize_path (path :Path )->Path :
    try :
        return path .resolve ()
    except (OSError ,RuntimeError ):
        return path
def should_exclude (entry_path :Path ,base :Path ,exclude_patterns :list [str ])->bool :
    try :
        rel =entry_path .relative_to (base )
    except ValueError :
        return False
    name =entry_path .name
    parts =rel .parts
    for pattern in exclude_patterns :
        pattern =pattern .strip ()
        if not pattern :
            continue
        if pattern .startswith ("*"):
            if any (re .search (pattern .replace ("*",".*"),p ,re .IGNORECASE )for p in parts ):
                return True
        elif pattern in parts or name ==pattern or pattern in name :
            return True
        if re .fullmatch (pattern .replace ("*",".*"),name ,re .IGNORECASE ):
            return True
    return False
def collect_tree (
root :Path ,
base :Path ,
max_depth :Optional [int ],
exclude :list [str ],
)->list [tuple [Path ,int ,bool ]]:
    root =normalize_path (root )
    base =normalize_path (base )
    default_exclude ={".git","__pycache__","node_modules",".venv","venv",".svn",".hg"}
    exclude_set =set (exclude )|default_exclude
    exclude_patterns =list (exclude_set )
    result :list [tuple [Path ,int ,bool ]]=[]
    def walk (current :Path ,depth :int )->None :
        if max_depth is not None and depth >max_depth :
            return
        try :
            entries =sorted (current .iterdir (),key =lambda p :(not p .is_dir (),p .name .lower ()))
        except PermissionError :
            logging .debug ("Нет доступа к каталогу %s",current )
            return
        for entry in entries :
            if should_exclude (entry ,base ,exclude_patterns ):
                continue
            if entry .name .startswith (".")and entry .name not in (".env",):
                if entry .is_dir ():
                    continue
            is_file =entry .is_file ()
            result .append ((entry ,depth ,is_file ))
            if entry .is_dir ():
                walk (entry ,depth +1 )
    walk (root ,0 )
    return result
def format_tree (
root :Path ,
base :Path ,
entries :list [tuple [Path ,int ,bool ]],
get_description :bool =True ,
)->list [str ]:
    lines :list [str ]=[]
    prefix_continue ="│   "
    prefix_branch ="├── "
    prefix_last ="└── "
    for i ,(path ,depth ,is_file )in enumerate (entries ):
        is_last_in_level =True
        for j in range (i +1 ,len (entries )):
            if entries [j ][1 ]==depth :
                is_last_in_level =False
                break
            if entries [j ][1 ]<depth :
                break
        prefix =(prefix_continue *depth )+(prefix_last if is_last_in_level else prefix_branch )
        name =path .name
        if path .is_dir ():
            name +="/"
        desc =""
        if get_description :
            if is_file :
                desc =get_file_description (path )
                if not desc :
                    desc =FILE_EXTENSIONS .get (path .suffix .lower (),"Файл")
            else :
                desc =get_dir_description (path )
                if not desc :
                    desc ="Каталог"
        if desc :
            padding =max (1 ,32 -len (prefix )-len (name ))
            line =f"{prefix }{name }{' '*padding }# {desc }"
        else :
            line =f"{prefix }{name }"
        lines .append (line )
    return lines
def run (
root :Path ,
tree_out :Path ,
dry_run :bool ,
force :bool ,
max_depth :Optional [int ],
exclude :list [str ],
verbose :bool ,
)->int :
    setup_logging (verbose )
    root =normalize_path (root )
    tree_out =normalize_path (tree_out )
    if not root .is_dir ():
        logging .error ("Каталог не найден: %s",root )
        return 1
    if tree_out .exists ()and not force and not dry_run :
        logging .error ("Файл уже существует: %s. Используйте --force для перезаписи.",tree_out )
        return 1
    entries =collect_tree (root ,root ,max_depth ,exclude )
    if not entries :
        lines =["# Дерево каталогов\n","\n","(пусто)\n"]
    else :
        lines_formatted =format_tree (root ,root ,entries ,get_description =True )
        lines =["# Дерево каталогов\n","\n"]+[line +"\n"for line in lines_formatted ]
    if dry_run :
        print ("План (--dry-run): будет записан файл",tree_out ,"содержимое:")
        out ="".join (lines )
        try :
            print (out )
        except UnicodeEncodeError :
            sys .stdout .buffer .write (out .encode ("utf-8"))
            sys .stdout .buffer .flush ()
        return 0
    try :
        tree_out .write_text ("".join (lines ),encoding ="utf-8")
        logging .info ("Записано: %s",tree_out )
        return 0
    except OSError as e :
        logging .error ("Ошибка записи %s: %s",tree_out ,e )
        return 1
def main ()->int :
    if sys .stdout .encoding and sys .stdout .encoding .upper ()!="UTF-8":
        try :
            sys .stdout .reconfigure (encoding ="utf-8")
        except (AttributeError ,OSError ):
            pass
    parser =argparse .ArgumentParser (
    description ="Генерация tree.md — дерево каталогов в псевдографике с описаниями файлов.",
    )
    parser .add_argument (
    "root",
    nargs ="?",
    default =".",
    type =Path ,
    help ="Корневая папка для обхода (по умолчанию текущая)",
    )
    parser .add_argument (
    "--tree-out",
    type =Path ,
    default =None ,
    help ="Файл для сохранения tree.md (по умолчанию tree.md в корне обхода)",
    )
    parser .add_argument (
    "--dry-run",
    action ="store_true",
    help ="Не записывать файл, вывести план",
    )
    parser .add_argument (
    "--force",
    action ="store_true",
    help ="Перезаписать существующий tree.md",
    )
    parser .add_argument (
    "--max-depth",
    type =int ,
    default =None ,
    metavar ="N",
    help ="Максимальная глубина рекурсии",
    )
    parser .add_argument (
    "--exclude",
    action ="append",
    default =[],
    metavar ="PATTERN",
    help ="Паттерны/имена для исключения (можно несколько раз)",
    )
    parser .add_argument (
    "--verbose","-v",
    action ="store_true",
    help ="Подробный вывод",
    )
    args =parser .parse_args ()
    root =args .root if args .root !=Path (".")else Path (".").resolve ()
    tree_out =args .tree_out if args .tree_out is not None else root /"tree.md"
    return run (
    root =root ,
    tree_out =tree_out ,
    dry_run =args .dry_run ,
    force =args .force ,
    max_depth =args .max_depth ,
    exclude =args .exclude ,
    verbose =args .verbose ,
    )
if __name__ =="__main__":
    sys .exit (main ())