from django.shortcuts import render

# Create your views here.
import os
from django.conf import settings
from django.http import HttpResponse
from django.template import loader
from django.views import generic
from .models import FMUForm
from models.models import Experiment
from .predict_bert import predict_bert
from django.shortcuts import get_object_or_404, render

def index(request):
    template = loader.get_template('fmulab/index.html')
    exp_list = Experiment.objects.order_by('exp_num')[:]
    context = {
        'exp_list': exp_list,
        'form': FMUForm(),
    }
    #context['form'] = FMUForm()
    # return render(request, "fmulab/index.html", context)
    return HttpResponse(template.render(context, request))

def home(request):
    template = loader.get_template('fmulab/home.html')
    return HttpResponse(template.render({}, request))


class ResultsView(generic.DetailView):
    # model = Question
    template_name = 'polls/dashboard.html'


def dashboard(request):
    if request.method == "POST":
        # Get the posted form
        MyExp = FMUForm(request.POST)

        if MyExp.is_valid():

            exp_desc = MyExp.cleaned_data['exp_desc']
            # new_sentence =
            # 'Mocking kung fu pictures when they were a staple of exploitation theater programming was witty'  # 3
            # new_sentence = 'scattered over the course of 80 minutes'  # 1
            # new_sentence = 'introspective and entertaining'  # 3
            num_labels = 5
            max_length = 512
            model_path = os.path.join(settings.BASE_DIR, "static", "checkpoint-3000")
            print('model_path: ', model_path)
            exp_num = predict_bert(exp_desc, model_path, num_labels, max_length) + 1

            # Show the FMU tutorial based on the prediction
            template = loader.get_template('models/detail.html')
            experiment = get_object_or_404(Experiment, pk=exp_num)
            exp_list = Experiment.objects.order_by('exp_num')[:]
            context = {
                'exp_list': exp_list,
                'experiment': experiment,
            }
            return HttpResponse(template.render(context, request))

    else:
        form = FMUForm()
        return render(request, 'fmulab/index.html', form)
