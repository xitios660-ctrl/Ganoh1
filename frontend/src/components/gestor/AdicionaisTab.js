import React from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '../ui/card';
import { Button } from '../ui/button';
import { PlusCircle, Plus, Pencil, Trash2 } from 'lucide-react';

export function AdicionaisTab({ 
  adicionais, 
  onNewAdicional, 
  onEditAdicional, 
  onDeleteAdicional 
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <PlusCircle className="h-5 w-5 text-brand-600" />
            Gerenciar Adicionais
          </div>
          <Button size="sm" onClick={onNewAdicional}>
            <Plus className="h-4 w-4 mr-1" /> Novo Adicional
          </Button>
        </CardTitle>
      </CardHeader>
      <CardContent>
        <p className="text-sm text-muted-foreground mb-4">
          Gerencie os adicionais disponíveis para os itens do cardápio (ex: ovos, queijo, mel).
        </p>
        <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-3">
          {adicionais.map((adicional) => (
            <div key={adicional.id} className="flex items-center justify-between p-3 border rounded-lg">
              <div>
                <p className="font-medium">{adicional.name}</p>
                <p className="text-sm text-brand-600">R$ {adicional.price?.toFixed(2)}</p>
              </div>
              <div className="flex gap-1">
                <Button size="sm" variant="ghost" onClick={() => onEditAdicional(adicional)}>
                  <Pencil className="h-3 w-3" />
                </Button>
                <Button size="sm" variant="ghost" className="text-red-600" onClick={() => onDeleteAdicional(adicional.id)}>
                  <Trash2 className="h-3 w-3" />
                </Button>
              </div>
            </div>
          ))}
        </div>
        {adicionais.length === 0 && (
          <div className="text-center py-8 text-muted-foreground">
            <PlusCircle className="h-10 w-10 mx-auto mb-2 opacity-30" />
            <p>Nenhum adicional cadastrado</p>
            <p className="text-sm">Clique em "Novo Adicional" para começar</p>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

export default AdicionaisTab;
