"""Gallery app views."""
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import render
from django.urls import reverse

from .services import list_gallery_images
from .utils import list_media_folders


def index(request: HttpRequest) -> HttpResponse:
    """Gallery home: list all media folders from wallpapers directory."""
    folders, root = list_media_folders()
    
    enriched: list[dict] = []
    for entry in folders:
        enriched.append(
            {
                **entry,
                'gallery_url': reverse('gallery:detail', kwargs={'folder': entry['name']}),
            }
        )
    
    return render(request, 'gallery/index.html', {
        'folders': enriched,
        'root': str(root),
    })


def detail(request: HttpRequest, folder: str) -> HttpResponse:
    """Gallery detail: show all images for a specific folder."""
    try:
        context = list_gallery_images(folder)
    except (ValueError, FileNotFoundError) as e:
        raise Http404(str(e)) from e
    
    template_context = context.to_dict()
    template_context['folder'] = context.folder
    
    return render(request, 'gallery/detail.html', template_context)


def lightbox(request: HttpRequest, folder: str, filename: str) -> HttpResponse:
    """Lightbox view for a single image."""
    try:
        context = list_gallery_images(folder)
    except (ValueError, FileNotFoundError) as e:
        raise Http404(str(e)) from e
    
    # Find the requested image
    selected_image = None
    for img in context.images:
        if img['name'] == filename:
            selected_image = img
            break
    
    if not selected_image:
        raise Http404("Image not found")
    
    return render(request, 'gallery/lightbox.html', {
        'folder': context.folder,
        'title': context.title,
        'year': context.year,
        'image': selected_image,
        'all_images': context.images,
    })
