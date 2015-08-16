# -*- coding: utf-8 -*-
from os import path
from re import sub
from sys import stderr
from StringIO import StringIO
from tempfile import mkdtemp
from shutil import rmtree
from itertools import groupby
from collections import defaultdict
from shutil import copyfileobj
from urllib2 import urlopen
from contextlib import closing
from pandas import DataFrame
import gzip
from GEOTypes import GSE, GSM, GPL, GDS


class UnknownGEOTypeException(Exception):
    """
    Exception representing the GEO type that do not correspond to any known.
    """
    pass


def get_GEO(geo=None, filepath=None, destdir="./", how='full'):
    """Get the GEO entry directly from the GEO database or read it from SOFT file.

    :param geo: str -- GEO database identifier
    :param filepath: str -- path to local SOFT file
    :param destdir: str -- directory to download data
    :param how: str -- GSM download mode: full ...
    :returns: GEOType object -- object according to specified GEO type

    """
    if (geo is None and filepath is None):
        raise Exception("You have to specify filename or GEO accession!")
    if (geo is not None and filepath is not None):
        raise Exception("You can specify filename or GEO accession - not both!")

    if filepath is None:
        filepath, geotype = get_GEO_file(geo, destdir=destdir, how=how)
    else:
        geotype = filepath.split("/")[-1][:3]

    stderr.write("Parsing %s:\n" % filepath)
    if geotype == "GSM":
        return parse_GSM(filepath)
    elif geotype == "GSE":
        return parse_GSE(filepath)
    elif geotype == 'GPL':
        return parse_GPL(filepath)
    elif geotype == 'GDS':
        raise NotImplementedError("GDS parsing is not yet implemented" % geotype)
        return parse_GDS(filepath)
    else:
        raise NotImplementedError("Unknown GEO type: %s" % geotype)


def get_GEO_file(geo, destdir=None, annotate_gpl=False, how="full"):
    """Given GEO accession download corresponding SOFT file

    :param geo: str -- GEO database identifier
    :param destdir: str -- directory to download data
    :param how: str -- GSM download mode: full ...
    :returns: tuple -- path to downladed file, type of GEO object

    """
    geo = geo.upper()
    geotype = geo[:3]
    range_subdir = sub(r"\d{1,3}$", "nnn", geo)
    mode = 'wb'
    if destdir is None:
        tmpdir = mkdtemp()
        stderr.write("No destination directory specified."
                     " Temporary files will be downloaded at %s\n" % tmpdir)
    else:
        tmpdir = destdir

    if geotype == "GDS":
        gseurl = "ftp://ftp.ncbi.nlm.nih.gov/geo/{root}/{range_subdir}/{record}/soft/{record_file}"
        url = gseurl.format(root="datasets",
                            range_subdir=range_subdir,
                            record=geo,
                            record_file="%s.soft.gz" % geo)
        filepath = path.join(tmpdir, "{record}.soft.gz".format(record=geo))
    elif geotype == "GSE":
        gseurl = "ftp://ftp.ncbi.nlm.nih.gov/geo/{root}/{range_subdir}/{record}/soft/{record_file}"
        url = gseurl.format(root="series",
                            range_subdir=range_subdir,
                            record=geo,
                            record_file="%s_family.soft.gz" % geo)
        filepath = path.join(tmpdir, "{record}.soft.gz".format(record=geo))
    elif geotype == "GSM":
        gsmurl = "http://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?targ=self&acc={record}&form=text&view={how}"
        url = gsmurl.format(record=geo, how=how)
        filepath = path.join(tmpdir, "{record}.soft".format(record=geo))
        mode = 'w'
    elif geotype == "GPL":
        if annotate_gpl:
            gplurl = "ftp://ftp.ncbi.nlm.nih.gov/geo/{root}/{range_subdir}/{record}/annot/{record_file}"
            url = gseurl.format(root="platforms",
                                range_subdir=range_subdir,
                                record=geo,
                                record_file="%s.annot.gz" % geo)
            filepath = path.join(tmpdir, "{record}.annot.gz".format(record=geo))
            if not path.isfile(filepath):
                with closing(urlopen(url)) as r:
                    with open(filepath, mode=mode) as f:
                        stderr.write("Downloading %s to %s\n" % (url, filepath))
                        copyfileobj(r, f)
            else:
                stderr.write("File already exist: using local version.\n")
            return filepath, geotype

        gseurl = "http://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?targ=self&acc={record}&form=text&view={how}"
        url = gseurl.format(record=geo, how=how)
        filepath = path.join(tmpdir, "{record}.soft".format(record=geo))
        mode = 'w'
        if not path.isfile(filepath):
            with closing(urlopen(url)) as r:
                with open(filepath, mode=mode) as f:
                    stderr.write("Downloading %s to %s\n" % (url, filepath))
                    copyfileobj(r, f)
        else:
            stderr.write("File already exist: using local version.\n")
        return filepath, geotype
    else:
        raise UnknownGEOTypeException("%s type is not known" % geotype)

    if not path.isfile(filepath):
        with closing(urlopen(url)) as r:
            with open(filepath, mode=mode) as f:
                stderr.write("Downloading %s to %s\n" % (url, filepath))
                copyfileobj(r, f)
    else:
        stderr.write("File already exist: using local version.\n")

    return filepath, geotype

def __parse_entry(entry_line):
    """Parse the SOFT file entry name line that starts with '^', '!' or '#'.

    :param entry_line: str -- line from SOFT file
    :returns: tuple -- type, value

    """
    if entry_line.startswith("!"):
        entry_line = sub(r"!\w*?_", '', entry_line)
    else:
        entry_line = entry_line.strip()[1:]
    try:
        entry_type, entry_name = [i.strip() for i in entry_line.split("=", 1)]
    except ValueError:
        entry_type = [i.strip() for i in entry_line.split("=", 1)][0]
        entry_name = ''
    return entry_type, entry_name


def parse_entry_name(nameline):
    """Parse line that starts with ^ and assign the name to it

    :param nameline: str -- line to process
    :returns: str -- entry name

    """
    entry_type, entry_name = __parse_entry(nameline)
    return entry_name

def parse_metadata(lines):
    """Parse list of lines with metadata information from SOFT file

    :param lines: iterable -- iterator over lines
    :returns: dict -- metadata from SOFT file

    """
    meta = defaultdict(list)
    for line in lines:
        line = line.rstrip()
        if line.startswith("!"):
            if "_table_begin" in line or "_table_end" in line:
                continue
            key, value = __parse_entry(line)
            meta[key].append(value)

    return dict(meta)


def parse_columns(lines):
    """Parse list of line with columns description from SOFT file

    :param lines: iterable -- iterator over lines
    :returns: pandas.DataFrame -- columns description

    """
    data = []
    index = []
    for line in lines:
        line = line.rstrip()
        if line.startswith("#"):
            tmp = __parse_entry(line)
            data.append(tmp[1])
            index.append(tmp[0])

    return DataFrame(data, index=index, columns=['description'])


def parse_table_data(lines):
    """Parse list of lines from SOFT file into DataFrame

    :param lines: iterable -- iterator over lines
    :returns: pandas.DataFrame -- table data

    """
    # filter lines that do not start with symbols
    data = "\n".join([i.rstrip() for i in lines if i[0] not in ("^", "!", "#")])
    return DataFrame.from_csv(StringIO(data), index_col=None, sep="\t")

def parse_GSM(filepath, entry_name=None):
    """Parse GSM entry from SOFT file

    :param filepath: str or iterable -- path to file with 1 GSM entry or list of lines representing
                                    GSM from GSE file
    :return: GSM object

    """
    if isinstance(filepath, str):
        if filepath[-2:] == "gz":
            mode = "rb"
            fopen = gzip.open
        else:
            mode = "r"
            fopen = open
        with fopen(filepath, mode) as f:
            soft = []
            has_table = False
            for line in f:
                if "_table_begin" in line or (line[0] not in ("^", "!", "#")):
                    has_table = True
                soft.append(line.rstrip())
    else:
        soft = []
        has_table = False
        for line in filepath:
            if "_table_begin" in line or (line[0] not in ("^", "!", "#")):
                has_table = True
            soft.append(line.rstrip())

    if entry_name is None:
        sets = [i for i in soft if i.startswith("^")]
        assert len(sets) == 1, "More than one entry in GPL"
        entry_name = parse_entry_name(sets[0])

    columns = parse_columns(soft)
    metadata = parse_metadata(soft)
    if has_table:
        table_data = parse_table_data(soft)
    else:
        table_data = DataFrame()

    gsm = GSM(name=entry_name,
              table=table_data,
              metadata=metadata,
              columns=columns)

    return gsm


def parse_GPL(filepath, entry_name=None):
    """Parse GPL entry from SOFT file

    :param filepath: str or iterable -- path to file with 1 GPL entry or list of lines representing
                                    GPL from GSE file
    :return: GPL object

    """
    if isinstance(filepath, str):
        if filepath[-2:] == "gz":
            mode = "rb"
            fopen = gzip.open
        else:
            mode = "r"
            fopen = open
        with fopen(filepath, mode) as f:
            soft = []
            has_table = False
            for line in f:
                if "_table_begin" in line or (line[0] not in ("^", "!", "#")):
                    has_table = True
                soft.append(line.rstrip())
    else:
        soft = []
        has_table = False
        for line in filepath:
            if "_table_begin" in line or (line[0] not in ("^", "!", "#")):
                has_table = True
            soft.append(line.rstrip())

    if entry_name is None:
        sets = [i for i in soft if i.startswith("^")]
        assert len(sets) == 1, "More than one entry in GPL"
        entry_name = parse_entry_name(sets[0])
    columns = parse_columns(soft)
    metadata = parse_metadata(soft)
    if has_table:
        table_data = parse_table_data(soft)
    else:
        table_data = DataFrame()

    gpl = GPL(name=entry_name,
              table=table_data,
              metadata=metadata,
              columns=columns)

    return gpl

def parse_GSE(filepath):
    """Parse GSE from SOFT file

    :param filepath: str -- path to GSE SOFT file
    :return: GSE object
    """
    if filepath[-2:] == "gz":
        mode = "rb"
        fopen = gzip.open
    else:
        mode = "r"
        fopen = open
    gpls = {}
    gsms = {}
    series_counter = 0
    with fopen(filepath, mode) as soft:
        groupper = groupby(soft, lambda x: x.startswith("^"))
        for is_new_entry, group in groupper:
            if is_new_entry:
                entry_type, entry_name = __parse_entry(group.next())
                stderr.write(" - %s : %s\n" % (entry_type.upper(), entry_name))
                if entry_type == "SERIES":
                    series_counter += 1
                    if series_counter > 1:
                        raise Exception("GSE file should contain only one series entry!")
                    is_data, data_group = groupper.next()
                    assert not is_data, "The key is not False, probably there is an error in the SOFT file"
                    metadata = parse_metadata(data_group)
                elif entry_type == "SAMPLE":
                    is_data, data_group = groupper.next()
                    gsms[entry_name] = parse_GSM(data_group, entry_name)
                elif entry_type == "PLATFORM":
                    is_data, data_group = groupper.next()
                    gpls[entry_name] = parse_GPL(data_group, entry_name)
                else:
                    stderr.write("Cannot recognize type %s\n" % entry_type)
    gse = GSE(name=entry_name,
              metadata=metadata,
              gpls=gpls,
              gsms=gsms)
    return gse



def parse_GDS(gds):
    """NOT IMPLEMENTED.
    Parse GDS from SOFT file

    :param gds: @todo
    :returns: @todo

    """
    pass