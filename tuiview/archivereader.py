import zipfile

def file_list_to_archive_strings(filenames):

    output_filename_list = []

    for filename in filenames:
        if filename.endswith('.gz') and filename.find(".tar.gz") == -1: # can process gz files but opening tar files in python (tarfile) takes ages
            output_filename_list.append(gz_to_file(filename))
        elif filename.endswith('.zip'):
            output_filename_list.extend(zip_to_file(filename))
        else:
            output_filename_list.append(filename)

    return output_filename_list

def gz_to_file(filename):
    """
    Converts a .gz filepath so that it can be opened with GDAL
    """
    return "/vsigzip/" + filename

def zip_to_file(filename):
    """
    Takes in a zip filename and if the zip contains BIL files then the filename will be converted
    so that it can be opened without extraction,
    """
    zip_file_list = []
    if zipfile.is_zipfile(filename):
        try:
            zip_file = zipfile.ZipFile(filename)
            zip_file_contents = ['/vsizip/{0}/{1}'.format(filename, zip_info_object.filename) for zip_info_object in zip_file.filelist if zip_info_object.filename.endswith('.bil')]
            zip_file_list.extend(zip_file_contents)
            zip_file.close()
        except zipfile.BadZipfile:
            pass

    return zip_file_list

